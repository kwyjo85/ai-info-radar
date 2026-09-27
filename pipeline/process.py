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
DIRECTOR_PASS_SCORE = 75       # 항목별 점수 합이 이 이상이면 continue, 미만이면 redirect (1회 재작성)
DIRECTOR_LEARNINGS_KEY = "director_learnings"
DIRECTOR_LEARNINGS_MAX = 6     # 다음 작성 프롬프트에 넣는 최근 지적사항 수

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

근거 규칙: 원문에 없는 도구·명령어 옵션·버전·수치를 보태야 할 때는 그 자리에 [추정] 또는 [공식 문서 확인 필요]를
붙여 원문 근거와 작성자의 추론을 구분하세요. 원문에 없는 기능을 원문의 것처럼 쓰지 마세요.
사용자의 이메일·이름·회사 등 개인정보는 쓰지 마세요 (필요하면 "본인 이메일"처럼 일반 표현). 이 문서는 공개될 수 있습니다.

마크다운만 출력하세요. 다른 텍스트 금지.
{extra}
정보 항목:
제목: {title}
출처: {url}
내용:
{content}"""


# Director 패턴 (RondoFlow 참고): 초안을 원문과 대조해 continue / redirect / conclude 판정.
DIRECTOR_PROMPT = """당신은 구현 블루프린트 검토자입니다. 아래 [원문]을 근거로 작성된 [블루프린트 초안]을 검토하세요.
사용자 관심 주제: "{topic}"

항목별로 채점하세요 (합계 100):
- grounding (0~40): 초안의 도구·기능·수치·저장소 이름이 원문에 있거나 널리 알려진 사실인가.
  원문에 없는 기능·명령어·수치를 지어냈으면 크게 감점 (지어낸 것 1개당 -10 이상).
- actionable (0~30): 구현 단계가 명령어·설정·파일 수준으로 따라 할 수 있는가.
- format (0~15): 필수 섹션(쉽게 말하면, 이걸로 할 수 있는 것, 개요, 구현 가능성, 필요 도구, 구현 단계, 예상 공수, 리스크/유의점)이 모두 있는가.
- topic_fit (0~15): 관심 주제 관점의 활용이 들어 있는가.

conclude: 원문 자체가 구현할 거리를 주지 않으면 (홍보·소식·의견뿐, 도구/기법 정보 없음) true. 초안의 품질과 무관하게 원문만 보고 판단.
issues: 이 초안의 구체적 문제 (최대 5개, 각 한 문장)
instructions: 다시 쓴다면 무엇을 빼고/바꾸고/더할지 구체적 지시
lesson: 이 초안의 문제 중 "다른 어떤 원문의 블루프린트에도 적용될" 일반 작성 원칙이 있으면 한 문장, 없으면 빈 문자열.
  (좋은 예: "원문에 없는 CLI 옵션을 추측해 쓰지 말고 '공식 문서 확인 필요'로 표시한다". 나쁜 예: 특정 도구·주제 이름이 들어간 문장)

반드시 아래 형식의 JSON 객체만 출력하세요. 다른 텍스트 금지.
{{"grounding": 30, "actionable": 20, "format": 15, "topic_fit": 10, "conclude": false, "issues": ["..."], "instructions": "...", "lesson": "", "reason": "판정 이유 한 문장"}}

[원문]
제목: {title}
{content}

[블루프린트 초안]
{draft}"""


class NotActionableError(Exception):
    """Director가 원문에 구현할 거리가 없다고 판정 (항목은 뉴스로 강등됨)."""


def parse_json_object(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"JSON 객체를 찾을 수 없음: {text[:200]}")
    return json.loads(text[start:end + 1])


def direct(conn, title: str, content: str, draft: str) -> dict:
    """초안 판정 (sonnet). 판정은 모델의 한 단어 답이 아니라 항목별 점수 합으로 정함 (한 단어 판정은 비판과 모순되기 쉬웠음).

    검토 호출이 실패하면 초안을 막지 않도록 continue로 취급.
    """
    prompt = DIRECTOR_PROMPT.format(topic=topic.topic_text(conn), title=title, content=content, draft=draft)
    try:
        # sonnet: 생각 끈 haiku는 날조를 지적하면서도 고득점을 줬고, 생각 켠 haiku는 sonnet보다 느리고 비쌌음
        # (2026-09-27, 같은 초안 3건 비교: haiku 83/79/92, haiku+생각 63/70/79 ~100초, sonnet 68/82/92 ~40초)
        v = parse_json_object(llm.complete(prompt, model="sonnet", task="director"))
        caps = {"grounding": 40, "actionable": 30, "format": 15, "topic_fit": 15}
        score = sum(max(0, min(cap, int(v.get(k, 0)))) for k, cap in caps.items())
    except Exception as e:
        return {"verdict": "continue", "score": None, "issues": [], "lesson": "",
                "reason": f"검토 실패로 통과 처리 ({type(e).__name__})"}
    if v.get("conclude") is True:
        verdict = "conclude"
    else:
        verdict = "continue" if score >= DIRECTOR_PASS_SCORE else "redirect"
    issues = [str(i).strip()[:150] for i in (v.get("issues") or []) if str(i).strip()][:5]
    return {"verdict": verdict, "score": score, "issues": issues,
            "instructions": (v.get("instructions") or "").strip(), "lesson": (v.get("lesson") or "").strip()[:150],
            "reason": (v.get("reason") or "").strip()}


def _learnings(conn) -> list[str]:
    raw = storage.get_setting(conn, DIRECTOR_LEARNINGS_KEY)
    return json.loads(raw) if raw else []


def _bank_learning(conn, lesson: str) -> None:
    """redirect 때 Director가 뽑은 '일반 작성 원칙'만 최근순 보관 → 다음 작성 프롬프트에 들어감.

    항목별 지적(issues)은 넣지 않는다: 특정 글에만 맞는 지적이 다른 주제 블루프린트를 오염시켰음.
    """
    if not lesson:
        return
    merged = [lesson] + [x for x in _learnings(conn) if x != lesson]
    storage.set_setting(conn, DIRECTOR_LEARNINGS_KEY, json.dumps(merged[:DIRECTOR_LEARNINGS_MAX], ensure_ascii=False))


def _blueprint_prompt(conn, title: str, url: str, content: str, fix: dict | None = None) -> str:
    extra = ""
    if learned := _learnings(conn):
        extra += "\n작성 원칙 (지난 검토에서 배운 것):\n" + "\n".join(f"- {x}" for x in learned) + "\n"
    if fix:
        extra += ("\n이전 초안이 검토에서 반려되었습니다. 아래 지시에 따라 처음부터 다시 작성하세요.\n"
                  f"지적사항: {'; '.join(fix['issues'])}\n재작성 지시: {fix['instructions']}\n")
    return BLUEPRINT_PROMPT.format(topic=topic.topic_text(conn), title=title, url=url, content=content, extra=extra)


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
            results = parse_json_array(llm.complete(prompt, model="haiku", task="score"))
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
    초안은 Director(sonnet)가 원문과 대조해 판정: continue 저장 / redirect 1회 재작성 / conclude 강등(NotActionableError).
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
    content = content[:BLUEPRINT_CONTENT_CHARS]
    md = llm.complete(_blueprint_prompt(conn, title, row["url"], content), model="sonnet", task="blueprint")
    v = direct(conn, title, content, md)
    log.info("Director 판정 (id %d): %s %s점 — %s", item_id, v["verdict"], v["score"], v["reason"])

    if v["verdict"] == "conclude":
        _demote_to_news(conn, item_id)
        raise NotActionableError(v["reason"] or "원문에 구현할 거리가 없음")

    rounds = 1
    if v["verdict"] == "redirect":
        _bank_learning(conn, v["lesson"])
        md2 = llm.complete(_blueprint_prompt(conn, title, row["url"], content, fix=v), model="sonnet", task="blueprint")
        v2 = direct(conn, title, content, md2)
        rounds = 2
        log.info("Director 재판정 (id %d): %s %s점 — %s", item_id, v2["verdict"], v2["score"], v2["reason"])
        # 재작성본이 더 낮게 나오면 초안 유지 (점수 없으면 재작성본 우선)
        if v2["score"] is None or v["score"] is None or v2["score"] >= v["score"]:
            md, v = md2, v2

    note = f"검토: {v['verdict']} · {v['score'] if v['score'] is not None else '-'}점 · {rounds}회 작성"
    if v["verdict"] != "continue" and v["issues"]:
        note += "\n⚠️ 남은 지적사항: " + "; ".join(v["issues"])
    BLUEPRINT_DIR.mkdir(exist_ok=True)
    path = BLUEPRINT_DIR / f"{datetime.now():%Y-%m-%d}-{slugify(title)}.md"
    path.write_text(md + f"\n\n---\n원본: {row['url']}\n{note}\n")
    conn.execute("UPDATE items SET blueprint_path=? WHERE id=?", (str(path.relative_to(ROOT)), item_id))
    conn.commit()
    log.info("블루프린트 생성: %s (항목 id=%d, %s)", path.name, item_id, note.split("\n")[0])
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
        except NotActionableError as e:
            demoted += 1
            log.info("Director conclude → 뉴스로 강등, 블루프린트 생략 (id %d: %s)", r["id"], e)
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
