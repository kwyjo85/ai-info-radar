"""Threads API 토큰 발급/갱신 스크립트.

사용법:
  uv run python scripts/threads_auth.py auth      # 최초 발급 (브라우저 인증 → 장기 토큰 저장)
  uv run python scripts/threads_auth.py refresh   # 장기 토큰 갱신 (만료 임박 시)

auth 흐름:
  1. https://localhost:8000/callback 을 받는 간이 HTTPS 서버 실행 (self-signed 인증서 자동 생성)
  2. 브라우저에서 인증 URL 오픈 → 승인하면 code가 자동 수신됨
     (자동 수신 실패 시 리디렉션된 주소를 직접 붙여넣는 수동 모드로 폴백)
  3. code → 단기 토큰 → 60일 장기 토큰 교환 후 .env에 저장
"""

import ssl
import sys
import time
import subprocess
import threading
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
CERT_DIR = ROOT / "data" / "certs"

GRAPH = "https://graph.threads.net"
SCOPES = "threads_basic,threads_keyword_search"
REFRESH_BEFORE_DAYS = 7  # 만료 7일 전부터 갱신


# ---------- .env 유틸 ----------

def load_env() -> dict:
    if not ENV_PATH.exists():
        sys.exit(f".env 파일이 없습니다: {ENV_PATH}\n.env.example을 복사해 THREADS_APP_SECRET을 채워주세요.")
    return {k: (v or "") for k, v in dotenv_values(ENV_PATH).items()}


def set_env_keys(updates: dict) -> None:
    """기존 .env의 다른 값은 보존하면서 지정 키만 갱신."""
    lines = ENV_PATH.read_text().splitlines()
    remaining = dict(updates)
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else None
        if key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    for k, v in remaining.items():
        out.append(f"{k}={v}")
    ENV_PATH.write_text("\n".join(out) + "\n")


# ---------- self-signed 인증서 ----------

def ensure_cert() -> tuple[Path, Path] | None:
    cert, key = CERT_DIR / "localhost.pem", CERT_DIR / "localhost-key.pem"
    if cert.exists() and key.exists():
        return cert, key
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(key), "-out", str(cert),
                "-days", "3650", "-nodes",
                "-subj", "/CN=localhost",
                "-addext", "subjectAltName=DNS:localhost",
            ],
            check=True, capture_output=True,
        )
        return cert, key
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"[!] 인증서 생성 실패({e}) → 수동 복사 모드로 진행합니다.")
        return None


# ---------- 콜백 서버 ----------

class _CodeHandler(BaseHTTPRequestHandler):
    code_holder: dict = {}

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        code = qs.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if code:
            _CodeHandler.code_holder["code"] = code
            self.wfile.write("인증 코드 수신 완료. 이 창을 닫고 터미널로 돌아가세요.".encode())
        else:
            self.wfile.write("code 파라미터가 없습니다.".encode())

    def log_message(self, *args):
        pass


def receive_code_via_server(cert: Path, key: Path, timeout: int = 300) -> str | None:
    server = HTTPServer(("localhost", 8000), _CodeHandler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=cert, keyfile=key)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    server.timeout = 5

    print("[*] https://localhost:8000/callback 대기 중...")
    print("    브라우저에서 '연결이 비공개가 아닙니다' 경고가 뜨면 [고급] → [localhost로 이동]을 눌러주세요.")
    deadline = time.time() + timeout
    while time.time() < deadline and "code" not in _CodeHandler.code_holder:
        server.handle_request()
    server.server_close()
    return _CodeHandler.code_holder.get("code")


def receive_code_manually() -> str:
    print("\n[수동 모드] 브라우저 승인 후 리디렉션된 주소창의 전체 URL(또는 code 값)을 붙여넣으세요.")
    raw = input("URL 또는 code: ").strip()
    if raw.startswith("http"):
        code = parse_qs(urlparse(raw).query).get("code", [""])[0]
    else:
        code = raw
    return code.removesuffix("#_")


# ---------- 토큰 교환 ----------

def exchange_short_lived(env: dict, code: str) -> str:
    r = httpx.post(f"{GRAPH}/oauth/access_token", data={
        "client_id": env["THREADS_APP_ID"],
        "client_secret": env["THREADS_APP_SECRET"],
        "grant_type": "authorization_code",
        "redirect_uri": env["THREADS_REDIRECT_URI"],
        "code": code,
    })
    r.raise_for_status()
    data = r.json()
    print(f"[*] 단기 토큰 발급 완료 (user_id={data.get('user_id')})")
    return data["access_token"]


def exchange_long_lived(env: dict, short_token: str) -> tuple[str, int]:
    r = httpx.get(f"{GRAPH}/access_token", params={
        "grant_type": "th_exchange_token",
        "client_secret": env["THREADS_APP_SECRET"],
        "access_token": short_token,
    })
    r.raise_for_status()
    data = r.json()
    return data["access_token"], data.get("expires_in", 60 * 86400)


def refresh_long_lived(token: str) -> tuple[str, int]:
    r = httpx.get(f"{GRAPH}/refresh_access_token", params={
        "grant_type": "th_refresh_token",
        "access_token": token,
    })
    r.raise_for_status()
    data = r.json()
    return data["access_token"], data.get("expires_in", 60 * 86400)


def save_token(token: str, expires_in: int) -> None:
    expires_at = datetime.now() + timedelta(seconds=expires_in)
    set_env_keys({
        "THREADS_ACCESS_TOKEN": token,
        "THREADS_TOKEN_EXPIRES_AT": expires_at.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    print(f"[+] 장기 토큰 .env 저장 완료 (만료: {expires_at:%Y-%m-%d})")


def refresh_if_needed() -> bool:
    """만료 REFRESH_BEFORE_DAYS일 전이면 갱신. 수집기에서 매 실행 시 호출용."""
    env = load_env()
    token = env.get("THREADS_ACCESS_TOKEN", "")
    expires_raw = env.get("THREADS_TOKEN_EXPIRES_AT", "")
    if not token:
        print("[!] 토큰이 없습니다. 먼저 auth를 실행하세요.")
        return False
    if expires_raw:
        expires_at = datetime.fromisoformat(expires_raw)
        if expires_at - datetime.now() > timedelta(days=REFRESH_BEFORE_DAYS):
            return True  # 아직 여유 있음
    new_token, expires_in = refresh_long_lived(token)
    save_token(new_token, expires_in)
    print("[+] 토큰 갱신 완료")
    return True


# ---------- 메인 ----------

def cmd_auth() -> None:
    env = load_env()
    if not env.get("THREADS_APP_SECRET"):
        sys.exit(".env의 THREADS_APP_SECRET을 먼저 채워주세요.")

    auth_url = (
        "https://threads.net/oauth/authorize"
        f"?client_id={env['THREADS_APP_ID']}"
        f"&redirect_uri={env['THREADS_REDIRECT_URI']}"
        f"&scope={SCOPES}&response_type=code"
    )
    print(f"[*] 인증 URL:\n    {auth_url}\n")

    code = None
    cert_pair = ensure_cert()
    if cert_pair:
        threading.Timer(1.0, webbrowser.open, args=(auth_url,)).start()
        code = receive_code_via_server(*cert_pair)
    else:
        webbrowser.open(auth_url)

    if not code:
        code = receive_code_manually()
    if not code:
        sys.exit("[!] code를 얻지 못했습니다.")

    short = exchange_short_lived(env, code)
    long_token, expires_in = exchange_long_lived(env, short)
    save_token(long_token, expires_in)

    # 토큰 검증
    r = httpx.get(f"{GRAPH}/v1.0/me", params={
        "fields": "id,username",
        "access_token": long_token,
    })
    if r.status_code == 200:
        me = r.json()
        print(f"[+] 검증 성공: @{me.get('username')} (id={me.get('id')})")
    else:
        print(f"[!] 검증 실패: {r.status_code} {r.text}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "auth"
    if cmd == "auth":
        cmd_auth()
    elif cmd == "refresh":
        refresh_if_needed()
    else:
        sys.exit(f"알 수 없는 명령: {cmd} (auth | refresh)")


if __name__ == "__main__":
    main()
