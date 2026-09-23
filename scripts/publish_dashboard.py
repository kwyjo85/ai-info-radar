"""radar 대시보드를 GitHub Pages(gh-pages 브랜치)에 배포.

items·블루프린트·현재 주제를 JSON으로 묶어 비밀번호로 암호화(PBKDF2-SHA256 + AES-256-GCM,
site/index.html 및 ig-dashboard와 같은 형식)한 뒤, 임시 디렉토리에서 커밋 1개짜리 브랜치를 만들어
원격 gh-pages에 force-push 한다. 매 배포가 히스토리를 덮어쓰므로 30분마다 배포해도 저장소가 커지지 않음.
매 사이클 끝(scripts/cycle.py)에서 호출됨.

.env:
  RADAR_SITE_REPO           배포 대상 원격 (기본: 이 저장소의 origin). origin도 없으면 배포 건너뜀
  RADAR_SITE_BRANCH         기본 gh-pages
  RADAR_DASHBOARD_PASSWORD  잠금 비밀번호 (없으면 IG_DASHBOARD_PASSWORD 재사용)

실행: uv run python -m scripts.publish_dashboard [--no-push] [--out DIR]
"""

import base64
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values

from collectors import storage
from pipeline import topic

SITE_SRC = ROOT / "site"
EXTRA_PAGES = [ROOT / "docs" / "architecture.html"]  # 함께 올릴 정적 페이지
PBKDF2_ITER = 200_000

log = logging.getLogger("publish")


def build_payload(conn) -> dict:
    rows = conn.execute(
        """SELECT id, score, kind, category, status, source, title, summary, easy, use_cases, url, author,
                  published_at, collected_at, topic, blueprint_path FROM items"""
    ).fetchall()
    items, blueprints = [], {}
    for r in rows:
        d = dict(r)
        bp = d.pop("blueprint_path")
        d["blueprint"] = None
        if bp and (ROOT / bp).exists():
            name = Path(bp).name
            d["blueprint"] = name
            blueprints.setdefault(name, (ROOT / bp).read_text())
        items.append(d)
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "topic": topic.topic_text(conn),
        "topicInfo": topic.get_topic(conn),
        "items": items,
        "blueprints": blueprints,
    }


def encrypt_bundle(payload: dict, password: str) -> dict:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(hashes.SHA256(), 32, salt, PBKDF2_ITER).derive(password.encode("utf-8"))
    ct = AESGCM(key).encrypt(iv, json.dumps(payload, ensure_ascii=False).encode("utf-8"), None)
    b64 = lambda b: base64.b64encode(b).decode()
    return {"v": 1, "kdf": "PBKDF2-SHA256", "iter": PBKDF2_ITER, "salt": b64(salt), "iv": b64(iv),
            "ct": b64(ct), "builtAt": payload["generatedAt"]}


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=180)


def write_site(out: Path, payload: dict, bundle: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(SITE_SRC / "index.html", out / "index.html")
    for page in EXTRA_PAGES:
        if page.exists():
            shutil.copy(page, out / page.name)
    (out / "data.enc.json").write_text(json.dumps(bundle))
    (out / ".nojekyll").touch()
    (out / "README.md").write_text(
        "# AI Info Radar — dashboard\n\n배포 전용 브랜치(gh-pages). 데이터는 AES-256-GCM으로 암호화되어 비밀번호가 필요합니다.\n"
        "소스 코드는 main 브랜치.\n\n"
        f"Updated: {payload['generatedAt']} · {len(payload['items'])} items · {len(payload['blueprints'])} blueprints\n"
    )


def publish(push: bool = True, out_dir: Path | None = None) -> Path | None:
    env = dotenv_values(ROOT / ".env")
    repo = (env.get("RADAR_SITE_REPO") or "").strip() or _git(ROOT, "remote", "get-url", "origin").stdout.strip()
    branch = (env.get("RADAR_SITE_BRANCH") or "gh-pages").strip()
    password = (env.get("RADAR_DASHBOARD_PASSWORD") or env.get("IG_DASHBOARD_PASSWORD") or "").strip()
    if push and not repo:
        log.info("배포 원격 없음(RADAR_SITE_REPO 또는 git origin) — 대시보드 배포 건너뜀")
        return None
    if not password:
        log.warning("대시보드 비밀번호 없음(RADAR_DASHBOARD_PASSWORD/IG_DASHBOARD_PASSWORD) — 배포 건너뜀")
        return None

    conn = storage.connect()
    payload = build_payload(conn)
    conn.close()
    bundle = encrypt_bundle(payload, password)

    tmp = None
    out = out_dir or Path(tmp := tempfile.mkdtemp(prefix="radar-pages-"))
    try:
        write_site(out, payload, bundle)
        if not push:
            log.info("빌드 완료 (push 생략): %s — %d items, %d blueprints", out, len(payload["items"]), len(payload["blueprints"]))
            return out
        for args in (("init", "-q", "-b", branch), ("add", "-A"),
                     ("-c", "user.name=ai-info-radar", "-c", "user.email=radar@localhost",
                      "commit", "-q", "-m", f"deploy {payload['generatedAt']} ({len(payload['items'])} items)")):
            r = _git(out, *args)
            if r.returncode != 0:
                raise RuntimeError(f"git {args[0]} 실패: {r.stderr.strip()[:300]}")
        r = _git(out, "push", "--force", "-q", repo, f"HEAD:refs/heads/{branch}")
        if r.returncode != 0:
            raise RuntimeError(f"push 실패: {r.stderr.strip()[:300]}")
        log.info("대시보드 배포 완료 → %s (%s): %d items, %d blueprints", repo, branch, len(payload["items"]), len(payload["blueprints"]))
        return out
    finally:
        if tmp and push:
            shutil.rmtree(tmp, ignore_errors=True)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else None
    publish(push="--no-push" not in sys.argv, out_dir=out)


if __name__ == "__main__":
    main()
