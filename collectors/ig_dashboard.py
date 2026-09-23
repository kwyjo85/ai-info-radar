"""인스타 대시보드(kwyjo85.github.io/ig-dashboard) 데이터 수집기.

대시보드 데이터(data.enc.json)는 비밀번호 기반 AES-256-GCM(PBKDF2-SHA256)으로 암호화되어 있다.
.env에 IG_DASHBOARD_PASSWORD가 있으면 매 사이클 파일을 내려받아 복호화하고, 결과를
data/ig_export.json에 캐시한다. 비밀번호가 없거나 실패하면 캐시 파일(수동 내보내기 포함)을 읽는다.

posts[] 필드(대시보드 JS 기준): id, url, source(saved|github), account, repo, lang, created,
date, caption, summary, tools[], types[], keywords[], analysis{score, verdict, idea, why, gate,
guide[], feasibility, impact, effort, hype}, ghStars, ghDelta
"""

import base64
import json
import logging
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
EXPORT_PATH = ROOT / "data" / "ig_export.json"
DEFAULT_URL = "https://kwyjo85.github.io/ig-dashboard/data.enc.json"

log = logging.getLogger(__name__)


def decrypt_bundle(enc: dict, password: str) -> dict:
    """대시보드 index.html의 decrypt()와 동일: PBKDF2-SHA256 → AES-256-GCM (ct 끝에 16바이트 태그)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=base64.b64decode(enc["salt"]),
        iterations=int(enc["iter"]),
    )
    key = kdf.derive(password.encode("utf-8"))
    plaintext = AESGCM(key).decrypt(base64.b64decode(enc["iv"]), base64.b64decode(enc["ct"]), None)
    return json.loads(plaintext.decode("utf-8"))


def fetch_and_decrypt() -> dict | None:
    """비밀번호가 설정되어 있으면 원격 파일을 복호화해 캐시에 저장하고 반환. 아니면 None."""
    env = dotenv_values(ROOT / ".env")
    password = (env.get("IG_DASHBOARD_PASSWORD") or "").strip()
    if not password:
        return None
    url = env.get("IG_DASHBOARD_URL") or DEFAULT_URL
    try:
        r = httpx.get(url, timeout=30, follow_redirects=True)
        r.raise_for_status()
        data = decrypt_bundle(r.json(), password)
    except Exception as e:
        # 비밀번호 오류는 InvalidTag로 나타남. 캐시로 폴백하되 원인은 남김
        log.warning("ig_dashboard: 원격 복호화 실패 (%s: %s) — 캐시 파일로 대체", type(e).__name__, e)
        return None
    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    log.info("ig_dashboard: 원격 데이터 복호화 완료 (updatedAt=%s)", data.get("updatedAt"))
    return data


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
    data = fetch_and_decrypt()
    if data is None:
        if not EXPORT_PATH.exists():
            log.info("ig_dashboard: 비밀번호/캐시 없음, 건너뜀 (.env IG_DASHBOARD_PASSWORD 설정)")
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
