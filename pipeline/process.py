"""처리기: 신규 항목 관련도 점수·분류·요약 → 고득점 항목 블루프린트 생성.

실행: uv run python -m pipeline.process
"""

import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors import storage
from pipeline import llm

BLUEPRINT_DIR = ROOT / "blueprints"
LOG_DIR = ROOT / "logs"

SCORE_BATCH = 10          # 점수 매기기 한 번에 묶는 항목 수
MAX_ITEMS_PER_RUN = 30    # 한 실행당 처리 상한 (구독 사용량 보호)
BLUEPRINT_THRESHOLD = 70
MAX_BLUEPRINTS_PER_RUN = 5

CATEGORIES = ["업무자동화", "AI에이전트", "개발도구", "노코드", "LLM활용", "기타"]

NEWS_SCORE_CAP = 60       # kind='뉴스' 항목의 점수 상한 (블루프린트 생성 제외)

SCORE_PROMPT = """당신은 "AI 기반 업무 효율화·자동화" 정보 큐레이터입니다.
아래 수집 항목들을 두 축으로 평가하세요.

1) relevance (0~100): AI 기반 업무 효율화·자동화 주제와의 관련도
2) actionability (0~100): 개인/소규모 팀이 "직접 구현·구축할 수 있는" 정도
   - 높음: 구체적 기법, 오픈소스 도구, 워크플로우 설계, 코드/설정 예시, 재현 가능한 사례
   - 낮음: 제품 출시 소식, 기능 업데이트 안내, 인용/의견/감상, 홍보, 랜딩페이지만 있는 소개
3) kind: "구현" (기법/도구/워크플로우 — 만들 것이 있음) 또는 "뉴스" (소식/의견/홍보 — 읽고 참고만 함)
   판단 기준: "이 글을 보고 내 맥북에서 코드를 짜거나 설정을 구성할 것이 있는가?" 없으면 뉴스.

각 항목에 대해:
- relevance, actionability: 위 정의대로 정수
- kind: "구현" | "뉴스"
- category: {categories} 중 하나
- summary: 한국어 3줄 요약 (줄바꿈 \\n 구분)

반드시 아래 형식의 JSON 배열만 출력하세요. 다른 텍스트 금지.
[{{"id": 1, "relevance": 85, "actionability": 70, "kind": "구현", "category": "업무자동화", "summary": "..."}}]

수집 항목:
{items}"""


def final_score(relevance: int, actionability: int, kind: str) -> int:
    """관련도 40% + 실행가능성 60%. 뉴스류는 상한을 둬 블루프린트 임계치(70)를 넘지 못하게 함."""
    score = round(0.4 * relevance + 0.6 * actionability)
    if kind == "뉴스":
        score = min(score, NEWS_SCORE_CAP)
    return max(0, min(100, score))

BLUEPRINT_PROMPT = """당신은 AI 자동화 구현 컨설턴트입니다. 아래 정보 항목을 개인 MacBook 환경에서
실제로 구현하기 위한 블루프린트를 한국어 마크다운으로 작성하세요.

구성 (이 순서대로):
# (제목)
## 개요 — 무엇을 자동화하는가, 어떤 가치가 있는가 (2~3문장)
## 구현 가능성 — 상/중/하 + 근거
## 필요 도구 — 구체적 도구/API/라이브러리 목록 (비용 여부 표시)
## 구현 단계 — 번호 목록, 각 단계는 실행 가능한 수준으로 구체적으로
## 예상 공수 — 시간 단위 추정 + 난이도
## 리스크/유의점

마크다운만 출력하세요. 다른 텍스트 금지.

정보 항목:
제목: {title}
출처: {url}
내용:
{content}"""


def setup_logging():
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(LOG_DIR / "process.log")],
    )


def parse_json_array(text: str) -> list:
    """응답에서 JSON 배열 부분만 추출해 파싱."""
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"JSON 배열을 찾을 수 없음: {text[:200]}")
    return json.loads(text[start:end + 1])


def slugify(text: str, max_len: int = 50) -> str:
    slug = re.sub(r"[^\w가-힣]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "item"


def score_items(conn, log) -> int:
    rows = conn.execute(
        "SELECT id, source, title, content FROM items WHERE status = 'new' ORDER BY id LIMIT ?",
        (MAX_ITEMS_PER_RUN,),
    ).fetchall()
    if not rows:
        return 0

    scored = 0
    for i in range(0, len(rows), SCORE_BATCH):
        batch = rows[i:i + SCORE_BATCH]
        payload = [
            {
                "id": r["id"],
                "source": r["source"],
                "title": r["title"] or "",
                "content": (r["content"] or "")[:500],
            }
            for r in batch
        ]
        prompt = SCORE_PROMPT.format(
            categories="/".join(CATEGORIES),
            items=json.dumps(payload, ensure_ascii=False, indent=1),
        )
        try:
            results = parse_json_array(llm.complete(prompt, model="haiku"))
        except Exception:
            log.exception("점수 배치 실패 (id %s~%s)", batch[0]["id"], batch[-1]["id"])
            continue

        now = datetime.now().isoformat(timespec="seconds")
        valid_ids = {r["id"] for r in batch}
        for res in results:
            if res.get("id") not in valid_ids:
                continue
            kind = res.get("kind") if res.get("kind") in ("구현", "뉴스") else "뉴스"
            conn.execute(
                """UPDATE items SET score=?, kind=?, category=?, summary=?, processed_at=?, status='processed'
                   WHERE id=?""",
                (
                    final_score(int(res.get("relevance", 0)), int(res.get("actionability", 0)), kind),
                    kind,
                    res.get("category", "기타"),
                    res.get("summary", ""),
                    now,
                    res["id"],
                ),
            )
            scored += 1
        conn.commit()
        log.info("점수 배치 완료: %d건 (누적 %d)", len(results), scored)
    return scored


def generate_blueprints(conn, log) -> int:
    rows = conn.execute(
        """SELECT id, title, url, content, summary FROM items
           WHERE status='processed' AND score >= ? AND blueprint_path IS NULL
             AND COALESCE(kind, '구현') = '구현'
           ORDER BY score DESC LIMIT ?""",
        (BLUEPRINT_THRESHOLD, MAX_BLUEPRINTS_PER_RUN),
    ).fetchall()
    if not rows:
        return 0

    BLUEPRINT_DIR.mkdir(exist_ok=True)
    made = 0
    for r in rows:
        title = r["title"] or (r["summary"] or "").split("\n")[0] or f"item-{r['id']}"
        prompt = BLUEPRINT_PROMPT.format(title=title, url=r["url"], content=(r["content"] or "")[:3000])
        try:
            md = llm.complete(prompt, model="sonnet")
        except Exception:
            log.exception("블루프린트 생성 실패 (id %d)", r["id"])
            continue
        path = BLUEPRINT_DIR / f"{datetime.now():%Y-%m-%d}-{slugify(title)}.md"
        path.write_text(md + f"\n\n---\n원본: {r['url']}\n")
        conn.execute("UPDATE items SET blueprint_path=? WHERE id=?", (str(path.relative_to(ROOT)), r["id"]))
        conn.commit()
        made += 1
        log.info("블루프린트 생성: %s (score 항목 id=%d)", path.name, r["id"])
    return made


def main():
    setup_logging()
    log = logging.getLogger("process")
    conn = storage.connect()

    scored = score_items(conn, log)
    made = generate_blueprints(conn, log)

    remaining = conn.execute("SELECT COUNT(*) FROM items WHERE status='new'").fetchone()[0]
    log.info("완료: 점수 %d건, 블루프린트 %d건, 미처리 잔여 %d건", scored, made, remaining)
    conn.close()


if __name__ == "__main__":
    main()
