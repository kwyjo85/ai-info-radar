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

from collectors import article, storage
from pipeline import llm, topic

BLUEPRINT_DIR = ROOT / "blueprints"
LOG_DIR = ROOT / "logs"

SCORE_BATCH = 10          # 점수 매기기 한 번에 묶는 항목 수
MAX_ITEMS_PER_RUN = 120   # 한 실행당 처리 상한 (구독 사용량 보호; 주제 변경 시 300건+ 재평가를 2~3사이클에 끝내기 위함)
BLUEPRINT_THRESHOLD = 80      # 이 점수 이상 구현 항목만 자동 생성 (그 아래는 텔레그램에서 요청 시 생성)
MAX_BLUEPRINTS_PER_RUN = 2
MAX_BLUEPRINTS_PER_DAY = 5     # 자동 생성 하루 상한 (그날 요청 생성분 포함해 셈)
MAX_BODY_ATTEMPTS_PER_RUN = 10 # 본문 없는 후보가 강등되며 넘어갈 수 있게, 한 실행에 살펴볼 후보 수
BLUEPRINT_CONTENT_CHARS = 6000

CATEGORIES = ["업무자동화", "AI에이전트", "개발도구", "노코드", "LLM활용", "기타"]

NEWS_SCORE_CAP = 60       # kind='뉴스' 항목의 점수 상한 (블루프린트 생성 제외)

SCORE_PROMPT = """당신은 정보 큐레이터입니다. 사용자가 현재 관심 있는 주제는 다음과 같습니다:
"{topic}"

아래 수집 항목들을 두 축으로 평가하세요.

1) relevance (0~100): 위 관심 주제와의 관련도 (주제와 무관하면 아무리 좋은 글이라도 낮게)
2) actionability (0~100): 개인/소규모 팀이 "직접 구현·구축할 수 있는" 정도
   - 높음: 구체적 기법, 오픈소스 도구, 워크플로우 설계, 코드/설정 예시, 재현 가능한 사례
   - 낮음: 제품 출시 소식, 기능 업데이트 안내, 인용/의견/감상, 홍보, 랜딩페이지만 있는 소개
3) kind: "구현" (기법/도구/워크플로우 — 만들 것이 있음) 또는 "뉴스" (소식/의견/홍보 — 읽고 참고만 함)
   판단 기준: "이 글을 보고 내 맥북에서 코드를 짜거나 설정을 구성할 것이 있는가?" 없으면 뉴스.

각 항목에 대해:
- relevance, actionability: 위 정의대로 정수
- kind: "구현" | "뉴스"
- title_ko: 한국어 제목 (원제가 영어면 자연스럽게 번역, 한국어면 다듬기; 40자 이내, 제품명·고유명사는 원문 유지)
- category: {categories} 중 하나
- summary: 한국어 3줄 요약 (줄바꿈 \\n 구분)
- easy: 전문용어 없이 처음 듣는 사람도 이해할 수 있게 "이게 뭔지"를 1~2문장으로. 비유를 써도 좋음.
  (예: "회의 녹음을 넣으면 알아서 회의록과 할 일 목록을 만들어주는 비서 같은 프로그램")
- use_cases: "이걸로 내가 할 수 있는 것" 구체적 예시 2~3개, 사용자 일상/업무 장면으로 서술, 줄바꿈 \\n 구분.
  (예: "매일 아침 받은 메일을 중요도별로 정리해 텔레그램으로 받기")

반드시 아래 형식의 JSON 배열만 출력하세요. 다른 텍스트 금지.
[{{"id": 1, "relevance": 85, "actionability": 70, "kind": "구현", "title_ko": "...", "category": "업무자동화", "summary": "...", "easy": "...", "use_cases": "...\\n..."}}]

수집 항목:
{items}"""


def final_score(relevance: int, actionability: int, kind: str) -> int:
    """관련도 40% + 실행가능성 60%. 뉴스류는 상한을 둬 블루프린트 자동 생성 임계치를 넘지 못하게 함."""
    score = round(0.4 * relevance + 0.6 * actionability)
    if kind == "뉴스":
        score = min(score, NEWS_SCORE_CAP)
    return max(0, min(100, score))

BLUEPRINT_PROMPT = """당신은 AI 자동화 구현 컨설턴트입니다. 아래 정보 항목을 개인 MacBook 환경에서
실제로 구현하기 위한 블루프린트를 한국어 마크다운으로 작성하세요.
사용자의 현재 관심 주제는 "{topic}"이며, 이 관점에서 어떻게 활용할지를 중심으로 서술하세요.

구성 (이 순서대로):
# (제목)
## 쉽게 말하면 — 전문용어 없이 처음 듣는 사람도 이해할 수 있게 2~3문장 (비유 환영)
## 이걸로 할 수 있는 것 — 사용자의 일상·업무 장면으로 구체적 예시 3개 (번호 목록, 각 1문장)
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
    # scripts.cycle이 수집→처리를 한 프로세스에서 돌리므로 collect.log 핸들러를 교체해야 함
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(LOG_DIR / "process.log")],
        force=True,
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
        """SELECT id, source, title, content FROM items WHERE status IN ('new', 'rescore')
           ORDER BY status = 'rescore', id LIMIT ?""",  # 신규 항목 먼저, 재평가는 남는 여유분으로
        (MAX_ITEMS_PER_RUN,),
    ).fetchall()
    if not rows:
        return 0

    current_topic = topic.topic_text(conn)
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
            topic=current_topic,
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
            # 점수는 채점 시점의 주제 기준이므로 topic도 그 시점 값으로 덮어씀
            conn.execute(
                """UPDATE items SET score=?, kind=?, category=?, summary=?, easy=?, use_cases=?, title_ko=?,
                                    processed_at=?, topic=?,
                                    status=CASE WHEN status='rescore' THEN 'briefed' ELSE 'processed' END
                   WHERE id=?""",
                (
                    final_score(int(res.get("relevance", 0)), int(res.get("actionability", 0)), kind),
                    kind,
                    res.get("category", "기타"),
                    res.get("summary", ""),
                    res.get("easy") or None,
                    "\n".join(res["use_cases"]) if isinstance(res.get("use_cases"), list) else (res.get("use_cases") or None),
                    (res.get("title_ko") or "").strip()[:80] or None,
                    now,
                    current_topic,
                    res["id"],
                ),
            )
            scored += 1
        conn.commit()
        log.info("점수 배치 완료: %d건 (누적 %d)", len(results), scored)
    return scored


class NoBodyError(Exception):
    """원문 본문을 얻지 못해 블루프린트를 만들 수 없음 (항목은 뉴스로 강등됨)."""


def ensure_body(conn, row) -> str | None:
    """블루프린트용 본문. 저장된 본문이 링크·메타데이터뿐이면 원문 페이지에서 가져와 DB에 저장.

    끝내 못 얻으면 None (HN 링크 글, Google 뉴스 리다이렉트 등).
    """
    content = article.html_to_text(row["content"])
    if not article.is_thin(content):
        return content
    body = article.fetch_body(row["url"])
    if body is None:
        return None
    merged = body + (f"\n\n---\n[피드 정보] {content}" if content else "")
    conn.execute("UPDATE items SET content=? WHERE id=?", (merged, row["id"]))
    conn.commit()
    return merged


def _demote_to_news(conn, item_id: int) -> None:
    """읽을 본문이 없는 항목은 '구현'으로 볼 근거가 없으므로 뉴스로 내리고 점수 상한 적용."""
    conn.execute(
        "UPDATE items SET kind='뉴스', score=MIN(COALESCE(score, 0), ?) WHERE id=?",
        (NEWS_SCORE_CAP, item_id),
    )
    conn.commit()


def make_blueprint(conn, item_id: int, log) -> Path:
    """항목 하나의 블루프린트를 생성해 저장하고 경로를 반환. 이미 있으면 그대로 반환.

    본문이 없으면 뉴스로 강등하고 NoBodyError. 텔레그램 봇의 요청 생성에서도 호출됨.
    """
    row = conn.execute(
        "SELECT id, COALESCE(title_ko, title) AS title, url, content, summary, blueprint_path FROM items WHERE id=?",
        (item_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"항목 {item_id} 없음")
    if row["blueprint_path"] and (ROOT / row["blueprint_path"]).exists():
        return ROOT / row["blueprint_path"]

    content = ensure_body(conn, row)
    if content is None:
        _demote_to_news(conn, item_id)
        raise NoBodyError(row["url"])

    title = row["title"] or (row["summary"] or "").split("\n")[0] or f"item-{row['id']}"
    prompt = BLUEPRINT_PROMPT.format(
        topic=topic.topic_text(conn), title=title, url=row["url"], content=content[:BLUEPRINT_CONTENT_CHARS]
    )
    md = llm.complete(prompt, model="sonnet")
    BLUEPRINT_DIR.mkdir(exist_ok=True)
    path = BLUEPRINT_DIR / f"{datetime.now():%Y-%m-%d}-{slugify(title)}.md"
    path.write_text(md + f"\n\n---\n원본: {row['url']}\n")
    conn.execute("UPDATE items SET blueprint_path=? WHERE id=?", (str(path.relative_to(ROOT)), item_id))
    conn.commit()
    log.info("블루프린트 생성: %s (항목 id=%d)", path.name, item_id)
    return path


def generate_blueprints(conn, log) -> int:
    """고득점(BLUEPRINT_THRESHOLD↑) 구현 항목만 자동 생성. 나머지는 텔레그램 [블루프린트 보기]로 요청 시 생성."""
    made_today = conn.execute(
        "SELECT COUNT(*) FROM items WHERE blueprint_path LIKE ?", (f"blueprints/{datetime.now():%Y-%m-%d}-%",)
    ).fetchone()[0]
    budget = min(MAX_BLUEPRINTS_PER_RUN, MAX_BLUEPRINTS_PER_DAY - made_today)
    if budget <= 0:
        return 0
    rows = conn.execute(
        """SELECT id FROM items
           WHERE status='processed' AND score >= ? AND blueprint_path IS NULL
             AND COALESCE(kind, '구현') = '구현' AND topic = ?
           ORDER BY score DESC LIMIT ?""",
        (BLUEPRINT_THRESHOLD, topic.topic_text(conn), MAX_BODY_ATTEMPTS_PER_RUN),
    ).fetchall()

    made = demoted = 0
    for r in rows:
        if made >= budget:
            break
        try:
            make_blueprint(conn, r["id"], log)
            made += 1
        except NoBodyError as e:
            demoted += 1
            log.info("본문 없음 → 뉴스로 강등, 블루프린트 생략 (id %d, %.80s)", r["id"], str(e))
        except Exception:
            log.exception("블루프린트 생성 실패 (id %d)", r["id"])
    if demoted:
        log.info("본문 없는 후보 %d건을 뉴스로 강등", demoted)
    return made


def main():
    setup_logging()
    log = logging.getLogger("process")
    conn = storage.connect()

    scored = score_items(conn, log)
    made = generate_blueprints(conn, log)

    remaining = conn.execute("SELECT COUNT(*) FROM items WHERE status IN ('new', 'rescore')").fetchone()[0]
    log.info("완료: 점수 %d건, 블루프린트 %d건, 미처리 잔여 %d건", scored, made, remaining)
    conn.close()


if __name__ == "__main__":
    main()
