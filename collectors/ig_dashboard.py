"""인스타 대시보드(kwyjo85.github.io/ig-dashboard) 데이터 가져오기.

대시보드 데이터는 비밀번호로 암호화되어 있어 직접 내려받을 수 없다. 대시보드를 열어 둔 브라우저
콘솔에서 `copy(JSON.stringify(IG_DATA))` 로 복사한 JSON을 data/ig_export.json 에 저장하면
이 수집기가 읽어 items로 넣는다. 파일이 없으면 조용히 건너뜀.

posts[] 필드(대시보드 JS 기준): id, url, source(instagram|github), account, repo, lang, created,
date, caption, summary, tools[], types[], keywords[], analysis{score, verdict, idea, why, gate,
guide[], feasibility, impact, effort, hype}, ghStars, ghDelta
"""

import json
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORT_PATH = ROOT / "data" / "ig_export.json"

log = logging.getLogger(__name__)


def _content(p: dict) -> str:
    """캡션·요약·대시보드 분석을 합쳐 채점/블루프린트가 쓸 본문을 만든다."""
    a = p.get("analysis") or {}
    parts = []
    if a.get("idea"):
        parts.append(f"[아이디어] {a['idea']}")
    if p.get("summary"):
        parts.append(f"[요약] {p['summary']}")
    if a:
        parts.append(
            f"[인스타 대시보드 평가] {a.get('score', '?')}/10 · {a.get('verdict', '')}"
            f" · 실현 {a.get('feasibility', '?')} 효과 {a.get('impact', '?')}"
            f" 난이도 {a.get('effort', '?')} 과장 {a.get('hype', '?')}"
        )
        if a.get("why"):
            parts.append(f"[근거] {a['why']}")
        if a.get("guide"):
            parts.append("[첫 단계] " + " → ".join(a["guide"][:5]))
    if p.get("tools"):
        parts.append("[도구] " + ", ".join(p["tools"]))
    if p.get("source") == "github":
        parts.append(f"[GitHub] {p.get('repo', '')} · {p.get('lang', '')} · ★{p.get('ghStars', '?')} (+{p.get('ghDelta', '?')})")
    if p.get("caption"):
        parts.append(f"[캡션] {p['caption']}")
    return "\n".join(parts)


def collect() -> list[dict]:
    if not EXPORT_PATH.exists():
        log.info("ig_dashboard: %s 없음, 건너뜀", EXPORT_PATH)
        return []
    data = json.loads(EXPORT_PATH.read_text())
    posts = data.get("posts", []) if isinstance(data, dict) else data

    items = []
    for p in posts:
        url = p.get("url")
        if not url:
            continue
        a = p.get("analysis") or {}
        is_gh = p.get("source") == "github"
        title = a.get("idea") or p.get("summary") or (p.get("caption") or "")[:80]
        items.append({
            "source": "github" if is_gh else "instagram",
            "external_id": str(p.get("id") or ""),
            "url": url,
            "author": p.get("repo") if is_gh else p.get("account"),
            "title": title[:200] if title else None,
            "content": _content(p)[:5000],
            "keyword": (p.get("keywords") or p.get("tools") or [None])[0],
            "published_at": p.get("date") or p.get("created"),
        })
    log.info("ig_dashboard: %d건 수집 (updatedAt=%s)", len(items), data.get("updatedAt") if isinstance(data, dict) else "?")
    return items
