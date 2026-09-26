"""현재 수집 주제 관리.

텔레그램에서 "주제 설정 : ..."을 보내면 set_topic()이 LLM으로 검색어를 확장해 settings에 저장하고,
수집기(threads/rss)와 처리기(점수 기준)가 다음 주제 변경까지 그 값을 읽는다.
주제가 없으면 config/keywords.yaml·feeds.yaml의 기본값을 쓴다.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors import storage
from collectors.storage import DEFAULT_TOPIC  # noqa: F401  (재노출)
from pipeline import llm

SETTING_KEY = "topic"

EXPAND_PROMPT = """사용자가 정보 수집 주제를 다음과 같이 설정했습니다:
"{topic}"

이 주제로 소셜/뉴스/영상을 검색할 때 쓸 검색어를 만들어 주세요.
- keywords_ko: 한국어 검색어 6~8개 (2~4단어, Threads/YouTube 검색용)
- keywords_en: 영어 검색어 6~8개 (2~4단어)
- hn_queries: Hacker News 검색용 짧은 영어 질의 3~4개. 첫 번째는 반드시 주제의 핵심 고유명사/제품명
  한 단어만 (예: "Jev", "n8n"). 나머지는 1~3단어로 넓게. 긴 질의는 검색 결과가 0건이 되므로 금지.
- unknown_terms: 주제에 포함된 단어 중 무엇을 가리키는지 확실히 알지 못하는 고유명사/약어 목록
  (있으면 그 단어는 검색어에 그대로 쓰고, 뜻을 추측해 변형하지 마세요. 없으면 빈 배열)

반드시 아래 형식의 JSON 객체만 출력하세요. 다른 텍스트 금지.
{{"keywords_ko": ["..."], "keywords_en": ["..."], "hn_queries": ["..."], "unknown_terms": []}}"""

REQUEUE_DAYS = 14  # 주제 변경 시 최근 N일 항목을 새 주제로 재평가

# 검색 피드(HN·Google 뉴스)가 연속으로 결과 0건인 횟수 {질의어: 횟수}. collectors/rss.py가 갱신.
EMPTY_STREAK_KEY = "rss_empty_streak"
EMPTY_STREAK_WARN = 12  # 30분 사이클 기준 약 6시간 연속 0건이면 쓸모없는 검색어로 봄


def _parse_json_object(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"JSON 객체를 찾을 수 없음: {text[:200]}")
    return json.loads(text[start:end + 1])


def get_topic(conn=None) -> dict | None:
    """저장된 주제 {topic, keywords_ko, keywords_en, hn_queries, set_at} 또는 None."""
    own = conn is None
    conn = conn or storage.connect()
    try:
        raw = storage.get_setting(conn, SETTING_KEY)
    finally:
        if own:
            conn.close()
    return json.loads(raw) if raw else None


def set_topic(text: str) -> dict:
    """주제 문장을 검색어로 확장해 저장. 확장 결과를 반환."""
    text = text.strip()
    if not text:
        raise ValueError("주제가 비어 있습니다")
    expanded = _parse_json_object(llm.complete(EXPAND_PROMPT.format(topic=text), model="haiku", task="topic"))
    data = {
        "topic": text,
        "keywords_ko": [k for k in expanded.get("keywords_ko", []) if k][:8],
        "keywords_en": [k for k in expanded.get("keywords_en", []) if k][:8],
        "hn_queries": [q for q in expanded.get("hn_queries", []) if q][:4],
        "unknown_terms": [t for t in expanded.get("unknown_terms", []) if t],
        "set_at": datetime.now().isoformat(timespec="seconds"),
    }
    conn = storage.connect()
    try:
        storage.set_setting(conn, SETTING_KEY, json.dumps(data, ensure_ascii=False))
        # 이미 채점된 최근 항목을 새 주제 기준으로 다시 평가하도록 되돌림.
        # 승인/스킵한 항목은 사용자 결정이므로 유지.
        cur = conn.execute(
            """UPDATE items SET status='new'
               WHERE status IN ('processed', 'briefed', 'rescore')
                 AND collected_at >= datetime('now', 'localtime', ?)""",
            (f"-{REQUEUE_DAYS} days",),
        )
        conn.commit()
        data["requeued"] = cur.rowcount
    finally:
        conn.close()
    return data


def clear_topic() -> None:
    conn = storage.connect()
    try:
        conn.execute("DELETE FROM settings WHERE key=?", (SETTING_KEY,))
        conn.commit()
    finally:
        conn.close()


def topic_text(conn=None) -> str:
    t = get_topic(conn)
    return t["topic"] if t else DEFAULT_TOPIC


def keywords(conn=None) -> list[str]:
    """Threads/YouTube 검색 키워드: 주제가 있으면 확장 키워드, 없으면 keywords.yaml."""
    t = get_topic(conn)
    if t:
        return t["keywords_ko"] + t["keywords_en"]
    return yaml.safe_load((ROOT / "config" / "keywords.yaml").read_text())["keywords"]


def hn_queries(conn=None) -> list[str]:
    """Hacker News 검색 질의: 주제가 있으면 확장 질의, 없으면 feeds.yaml의 hn_search_default."""
    t = get_topic(conn)
    if t:
        return t["hn_queries"]
    data = yaml.safe_load((ROOT / "config" / "feeds.yaml").read_text())
    return data.get("hn_search_default") or []


def empty_queries(conn=None) -> list[str]:
    """EMPTY_STREAK_WARN회 이상 연속으로 결과가 없는 검색어."""
    own = conn is None
    conn = conn or storage.connect()
    try:
        raw = storage.get_setting(conn, EMPTY_STREAK_KEY)
    finally:
        if own:
            conn.close()
    streaks = json.loads(raw) if raw else {}
    return [q for q, n in streaks.items() if n >= EMPTY_STREAK_WARN]


def format_topic(t: dict | None) -> str:
    if not t:
        return f"현재 주제: (기본) {DEFAULT_TOPIC}\nconfig/keywords.yaml · feeds.yaml 기본 검색어 사용 중"
    text = (
        f"현재 주제: {t['topic']}\n"
        f"설정 시각: {t['set_at'][:16].replace('T', ' ')}\n"
        f"검색어(한): {', '.join(t['keywords_ko'])}\n"
        f"검색어(영): {', '.join(t['keywords_en'])}\n"
        f"HN 검색: {', '.join(t['hn_queries'])}"
    )
    if t.get("unknown_terms"):
        text += (
            f"\n\n⚠️ '{', '.join(t['unknown_terms'])}'이(가) 무엇인지 확실하지 않아 검색어가 부정확할 수 있습니다. "
            "정확한 이름이나 설명을 붙여 다시 설정해 주세요.\n"
            "예) 주제 설정 : jev-router(Claude Code 모델 라우터)를 활용한 비용 절감"
        )
    if empty := empty_queries():
        text += (
            f"\n\n🔍 최근 {EMPTY_STREAK_WARN // 2}시간 넘게 결과가 없는 검색어: {', '.join(empty)}\n"
            "주제 문장을 조금 넓게 바꿔 다시 설정하면 검색어가 새로 만들어집니다."
        )
    return text
