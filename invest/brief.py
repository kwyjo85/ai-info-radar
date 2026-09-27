"""투자 정보 브리핑 (1단계: 조회 전용 정보 비서).

- 관심 종목(settings.invest_watchlist)의 종가·등락·20일선 대비, 주요 지수·환율, DART 공시, 뉴스 헤드라인
- LLM을 쓰지 않는다: 숫자는 모두 데이터 출처에서 그대로 가져오고 [출처·기준일]을 붙인다
- 매수·매도 판단은 하지 않는다. 원칙은 invest/rules.md (사람만 수정)

데이터 출처
- 시세·지수·환율: FinanceDataReader (키 불필요, 출처마다 갱신 시점이 달라 기준일을 항목별로 표시)
- 공시: DART OpenAPI (.env 의 DART_API_KEY, https://opendart.fss.or.kr 에서 무료 발급). 없으면 건너뜀
- 뉴스: Google 뉴스 RSS (헤드라인·링크만)

실행: uv run python -m invest.brief   (텔레그램 없이 콘솔로 확인)
"""

import datetime as dt
import io
import json
import logging
import re
import sys
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import html

import feedparser
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values

from collectors import storage

log = logging.getLogger("invest")

WATCHLIST_KEY = "invest_watchlist"   # [{"code": "005930", "name": "삼성전자", "market": "KR"}, ...]
WATCHLIST_MAX = 30
INDICES = [("KS11", "코스피"), ("KQ11", "코스닥"), ("US500", "S&P500"), ("IXIC", "나스닥"), ("USD/KRW", "원/달러")]
STALE_DAYS = 5          # 기준일이 이보다 오래되면 ⚠️ 표시 (연휴 고려)
NEWS_PER_STOCK = 3
NEWS_MAX_AGE_H = 36
DART_DAYS = 3           # 최근 N일 공시
CORP_CODE_CACHE = ROOT / "data" / "dart_corp_codes.json"

KR_CODE_RE = re.compile(r"^\d{6}$")
US_TICKER_RE = re.compile(r"^[A-Z][A-Z.\-]{0,9}$")


def _dart_key() -> str | None:
    return dotenv_values(ROOT / ".env").get("DART_API_KEY") or None


# ---------- 관심 종목 ----------

def get_watchlist(conn) -> list[dict]:
    raw = storage.get_setting(conn, WATCHLIST_KEY)
    return json.loads(raw) if raw else []


def _save_watchlist(conn, items: list[dict]) -> None:
    storage.set_setting(conn, WATCHLIST_KEY, json.dumps(items, ensure_ascii=False))


def _krx_listing():
    import FinanceDataReader as fdr
    return fdr.StockListing("KRX")[["Code", "Name"]]


def resolve_symbol(text: str) -> dict:
    """「005930」「삼성전자」「AAPL」 → {code, name, market}. 못 찾으면 ValueError."""
    q = text.strip()
    if KR_CODE_RE.match(q) or not US_TICKER_RE.match(q.upper()):
        listing = _krx_listing()
        hit = listing[listing.Code == q] if KR_CODE_RE.match(q) else listing[listing.Name == q]
        if hit.empty and not KR_CODE_RE.match(q):
            hit = listing[listing.Name.str.contains(q, regex=False)]
            if len(hit) > 1:
                names = ", ".join(f"{r.Name}({r.Code})" for r in hit.head(8).itertuples())
                raise ValueError(f"「{q}」에 해당하는 종목이 여러 개입니다: {names}\n종목코드로 다시 적어주세요.")
        if hit.empty:
            raise ValueError(f"「{q}」 종목을 한국거래소 목록에서 찾지 못했습니다.")
        r = hit.iloc[0]
        return {"code": r.Code, "name": r.Name, "market": "KR"}
    ticker = q.upper()
    if not _history(ticker, days=10).shape[0]:
        raise ValueError(f"「{ticker}」 시세를 찾지 못했습니다. 미국 티커가 맞는지 확인해주세요.")
    return {"code": ticker, "name": ticker, "market": "US"}


def add_to_watchlist(conn, text: str) -> tuple[dict, bool]:
    """(종목, 새로 추가됐는지)."""
    items = get_watchlist(conn)
    sym = resolve_symbol(text)
    if any(i["code"] == sym["code"] for i in items):
        return sym, False
    if len(items) >= WATCHLIST_MAX:
        raise ValueError(f"관심 종목은 최대 {WATCHLIST_MAX}개까지입니다.")
    items.append(sym)
    _save_watchlist(conn, items)
    return sym, True


def remove_from_watchlist(conn, text: str) -> dict | None:
    q = text.strip()
    items = get_watchlist(conn)
    hit = next((i for i in items if q in (i["code"], i["name"]) or i["code"] == q.upper()), None)
    if hit:
        _save_watchlist(conn, [i for i in items if i is not hit])
    return hit


def format_watchlist(items: list[dict]) -> str:
    if not items:
        return "관심 종목이 없습니다.\n추가: 「관심 추가 : 삼성전자」 또는 「관심 추가 : AAPL」"
    lines = [f"• {i['name']} ({i['code']}, {'국내' if i['market'] == 'KR' else '미국'})" for i in items]
    return f"관심 종목 {len(items)}개\n" + "\n".join(lines) + "\n\n추가/삭제: 「관심 추가 : 종목」 「관심 삭제 : 종목」"


# ---------- 시세 ----------

def _history(symbol: str, days: int = 60):
    import FinanceDataReader as fdr
    start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    return fdr.DataReader(symbol, start).dropna(subset=["Close"])


def quote(symbol: str) -> dict | None:
    """최근 두 거래일 종가로 등락을 직접 계산 (출처마다 Change 컬럼 의미가 달라서)."""
    try:
        df = _history(symbol)
    except Exception as e:
        log.warning("시세 조회 실패 %s: %s", symbol, e)
        return None
    if len(df) < 2:
        return None
    close, prev = float(df.Close.iloc[-1]), float(df.Close.iloc[-2])
    ma20 = float(df.Close.tail(20).mean()) if len(df) >= 20 else None
    return {
        "close": close,
        "change_pct": (close / prev - 1) * 100,
        "ma20_gap_pct": (close / ma20 - 1) * 100 if ma20 else None,
        "date": df.index[-1].date(),
    }


def _num(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:,.2f}"


def _date_tag(d: dt.date, today: dt.date) -> str:
    stale = (today - d).days > STALE_DAYS
    return f"{d:%m/%d}" + (" ⚠️오래됨" if stale else "")


def _arrow(pct: float) -> str:
    return "🔺" if pct > 0 else ("🔻" if pct < 0 else "▫️")


# ---------- DART 공시 ----------

def _corp_codes(key: str) -> dict[str, str]:
    """종목코드 → DART 고유번호. 전체 목록(zip)을 하루 1회 받아 캐시."""
    if CORP_CODE_CACHE.exists() and dt.date.fromtimestamp(CORP_CODE_CACHE.stat().st_mtime) == dt.date.today():
        return json.loads(CORP_CODE_CACHE.read_text())
    r = httpx.get("https://opendart.fss.or.kr/api/corpCode.xml", params={"crtfc_key": key}, timeout=60)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        root = ET.fromstring(z.read(z.namelist()[0]))
    mapping = {
        el.findtext("stock_code").strip(): el.findtext("corp_code")
        for el in root.iter("list") if (el.findtext("stock_code") or "").strip()
    }
    CORP_CODE_CACHE.write_text(json.dumps(mapping))
    return mapping


def disclosures(code: str, key: str, corp_codes: dict[str, str]) -> list[dict]:
    corp = corp_codes.get(code)
    if not corp:
        return []
    today = dt.date.today()
    r = httpx.get("https://opendart.fss.or.kr/api/list.json", params={
        "crtfc_key": key, "corp_code": corp,
        "bgn_de": (today - dt.timedelta(days=DART_DAYS)).strftime("%Y%m%d"), "end_de": today.strftime("%Y%m%d"),
        "page_count": 10,
    }, timeout=20)
    data = r.json()
    if data.get("status") not in ("000", "013"):   # 013 = 조회된 데이터 없음
        raise RuntimeError(f"DART {data.get('status')}: {data.get('message')}")
    return [
        {"title": d["report_nm"].strip(), "date": d["rcept_dt"],
         "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={d['rcept_no']}"}
        for d in data.get("list", [])
    ]


# ---------- 뉴스 ----------

def news(item: dict) -> list[dict]:
    q = f'"{item["name"]}"' if item["market"] == "KR" else f"{item['code']} stock"
    lang = "hl=ko&gl=KR&ceid=KR:ko" if item["market"] == "KR" else "hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}+when:2d&{lang}")
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=NEWS_MAX_AGE_H)
    out = []
    for e in feed.entries:
        if not e.get("published_parsed"):
            continue
        pub = dt.datetime(*e.published_parsed[:6], tzinfo=dt.timezone.utc)
        if pub >= cutoff:
            out.append({"title": e.title, "url": e.link, "pub": pub})
    return sorted(out, key=lambda x: x["pub"], reverse=True)[:NEWS_PER_STOCK]


# ---------- 브리핑 ----------

def _link(title: str, url: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(title)}</a>'


def build_brief(conn) -> list[str]:
    """텔레그램 메시지 목록 (parse_mode=HTML). 첫 메시지는 지수·요약, 이후 종목별 1개."""
    today = dt.date.today()
    items = get_watchlist(conn)

    lines = [f"📈 투자 정보 브리핑 ({today:%m/%d})", "※ 조회 전용 정보입니다. 매매 판단은 invest/rules.md 기준으로 직접 하세요.", ""]
    lines.append("🌐 지수·환율 [출처 FinanceDataReader · 기준일]")
    for sym, label in INDICES:
        q = quote(sym)
        lines.append(
            f"• {label} {_num(q['close'])} {_arrow(q['change_pct'])}{q['change_pct']:+.2f}% [{_date_tag(q['date'], today)}]"
            if q else f"• {label} [미확인: 조회 실패]"
        )
    if not items:
        lines += ["", format_watchlist(items)]
        return [html.escape("\n".join(lines))]

    key = _dart_key()
    corp_codes, dart_note = {}, None
    if not key:
        dart_note = "DART 공시: .env 에 DART_API_KEY 가 없어 건너뜀 (opendart.fss.or.kr 무료 발급)"
    else:
        try:
            corp_codes = _corp_codes(key)
        except Exception as e:
            log.warning("DART 고유번호 목록 실패: %s", e)
            dart_note = f"DART 공시: 조회 실패 ({type(e).__name__})"

    lines += ["", f"📋 관심 종목 {len(items)}개 [종가 · 전일 대비 · 20일 평균 대비 · 기준일]"]
    detail_msgs = []
    for it in items:
        q = quote(it["code"])
        unit = "원" if it["market"] == "KR" else "$"
        if q:
            gap = f" · 20일선 {q['ma20_gap_pct']:+.1f}%" if q["ma20_gap_pct"] is not None else ""
            price = f"{_num(q['close'])}{unit}" if unit == "원" else f"{unit}{_num(q['close'])}"
            lines.append(f"• {it['name']} {price} {_arrow(q['change_pct'])}{q['change_pct']:+.2f}%{gap} [{_date_tag(q['date'], today)}]")
        else:
            lines.append(f"• {it['name']} [미확인: 시세 조회 실패]")

        section = []
        if it["market"] == "KR" and corp_codes:
            try:
                ds = disclosures(it["code"], key, corp_codes)
                if ds:
                    section.append(f"📑 공시 (최근 {DART_DAYS}일) [출처 DART]")
                    section += [f"• {d['date'][4:6]}/{d['date'][6:]} {_link(d['title'], d['url'])}" for d in ds]
            except Exception as e:
                section.append(f"📑 공시 [미확인: {html.escape(str(e))}]")
        try:
            ns = news(it)
        except Exception as e:
            log.warning("뉴스 실패 %s: %s", it["code"], e)
            ns = []
        if ns:
            section.append("📰 뉴스 헤드라인 [출처 Google 뉴스]")
            section += [f"• {_link(n['title'], n['url'])}" for n in ns]
        if section:
            detail_msgs.append(f"🔎 <b>{html.escape(it['name'])} ({it['code']})</b>\n" + "\n".join(section))

    if dart_note:
        lines += ["", dart_note]
    if not detail_msgs:
        lines += ["", "관심 종목의 최근 공시·뉴스가 없습니다."]
    return [html.escape("\n".join(lines))] + detail_msgs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    c = storage.connect()
    for m in build_brief(c):
        print(m, "\n" + "-" * 40)
