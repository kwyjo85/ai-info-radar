"""radar 대시보드를 GitHub Pages(gh-pages 브랜치)에 배포.

items·블루프린트·현재 주제를 JSON으로 묶어 비밀번호로 암호화(PBKDF2-SHA256 + AES-256-GCM,
site/index.html 및 ig-dashboard와 같은 형식)한 뒤, 임시 디렉토리에서 커밋 1개짜리 브랜치를 만들어
원격 gh-pages에 force-push 한다. 매 배포가 히스토리를 덮어쓰므로 30분마다 배포해도 저장소가 커지지 않음.
매 사이클 끝(scripts/cycle.py)에서 호출됨.

화면 파일(site/index.html 등)은 작업 폴더가 아니라 원격 main(origin/main)에 올라간 버전을 쓴다.
로컬에서 고치는 중인 화면이 사이클 때문에 먼저 공개되지 않도록 — main에 push해야 배포됨.
--no-push 로컬 빌드(미리보기)는 작업 폴더 파일을 그대로 쓴다.

데이터·화면·배포 대상이 직전 배포와 같으면 건너뛴다(대부분 사이클은 신규 0~1건).
단 HEARTBEAT_HOURS가 지나면 변경이 없어도 배포해 대시보드의 '갱신' 시각이 너무 오래되지 않게 한다.

.env:
  RADAR_SITE_REPO           배포 대상 원격 (기본: 이 저장소의 origin). origin도 없으면 배포 건너뜀
  RADAR_SITE_BRANCH         기본 gh-pages
  RADAR_DASHBOARD_PASSWORD  잠금 비밀번호 (없으면 IG_DASHBOARD_PASSWORD 재사용)
  RADAR_SITE_REF            화면 파일을 가져올 git ref (기본 origin/main)

실행: uv run python -m scripts.publish_dashboard [--no-push] [--out DIR]
"""

import base64
import hashlib
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

SITE_FILES = ["site/index.html", "docs/architecture.html"]  # 올릴 정적 페이지 (저장소 기준 경로, 첫 번째가 index)
PBKDF2_ITER = 200_000
HEARTBEAT_HOURS = 6
PUBLISH_STATE_KEY = "publish_state"  # settings: {"hash": 직전 배포 내용 해시, "at": 배포 시각}

log = logging.getLogger("publish")


def build_payload(conn) -> dict:
    rows = conn.execute(
        """SELECT id, score, kind, category, status, source, COALESCE(title_ko, title) AS title, title AS title_orig,
                  summary, easy, use_cases, url, author,
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


def content_hash(payload: dict, pages: dict[str, bytes], repo: str, branch: str) -> str:
    """배포 내용의 해시. generatedAt은 매번 바뀌므로 제외."""
    h = hashlib.sha256()
    data = {k: v for k, v in payload.items() if k != "generatedAt"}
    h.update(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    for name in sorted(pages):
        h.update(name.encode() + b"\0" + pages[name])
    h.update(f"{repo}\0{branch}".encode())
    return h.hexdigest()


def _unchanged_recently(conn, digest: str) -> bool:
    raw = storage.get_setting(conn, PUBLISH_STATE_KEY)
    if not raw:
        return False
    state = json.loads(raw)
    age = datetime.now(timezone.utc) - datetime.fromisoformat(state["at"])
    return state.get("hash") == digest and age.total_seconds() < HEARTBEAT_HOURS * 3600


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=180)


def site_files(ref: str | None) -> dict[str, bytes]:
    """배포할 정적 페이지 {파일명: 내용}. ref가 있으면 그 커밋의 버전, 없으면 작업 폴더 파일."""
    files = {}
    for rel in SITE_FILES:
        if ref:
            r = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=ROOT, capture_output=True, timeout=60)
            if r.returncode != 0:
                if rel == SITE_FILES[0]:
                    raise RuntimeError(f"{ref}에 {rel} 없음: {r.stderr.decode().strip()[:200]}")
                continue
            data = r.stdout
        elif (ROOT / rel).exists():
            data = (ROOT / rel).read_bytes()
        else:
            continue
        files[Path(rel).name] = data
    return files


def write_site(out: Path, payload: dict, bundle: dict, pages: dict[str, bytes]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, data in pages.items():
        (out / name).write_bytes(data)
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

    # 화면 파일은 원격 main 기준: 최신 main을 받아 온 뒤 그 버전을 씀 (fetch 실패 시 마지막으로 받은 main)
    ref = None
    if push:
        ref = (env.get("RADAR_SITE_REF") or "origin/main").strip()
        remote, _, rbranch = ref.partition("/")
        if rbranch:
            r = _git(ROOT, "fetch", "-q", remote, rbranch)
            if r.returncode != 0:
                log.warning("fetch 실패 — 마지막으로 받은 %s로 배포: %s", ref, r.stderr.strip()[:200])
    pages = site_files(ref)

    conn = storage.connect()
    try:
        payload = build_payload(conn)
        digest = content_hash(payload, pages, repo, branch)
        if push and _unchanged_recently(conn, digest):
            log.info("대시보드 변경 없음 — 배포 건너뜀 (%d items)", len(payload["items"]))
            return None
    finally:
        conn.close()
    bundle = encrypt_bundle(payload, password)

    tmp = None
    out = out_dir or Path(tmp := tempfile.mkdtemp(prefix="radar-pages-"))
    try:
        write_site(out, payload, bundle, pages)
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
        conn = storage.connect()
        try:
            storage.set_setting(conn, PUBLISH_STATE_KEY, json.dumps({"hash": digest, "at": payload["generatedAt"]}))
        finally:
            conn.close()
        site_rev = _git(ROOT, "rev-parse", "--short", ref).stdout.strip()
        log.info("대시보드 배포 완료 → %s (%s): %d items, %d blueprints, 화면 %s@%s",
                 repo, branch, len(payload["items"]), len(payload["blueprints"]), ref, site_rev)
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
