"""투자 신호 기록부 (2단계): 규칙 신호를 기록하고 5·20거래일 뒤 결과를 자동 채점.

목적은 "이 신호가 실제로 통하는가"를 재는 것 — 매매 추천이 아니다. 규칙은 측정 대상일 뿐이며
켜고 끄는 건 사용자가 텔레그램으로 한다.

- 앞으로 일어나는 신호만 기록 (포워드 테스트): 관심 종목에 추가한 날 이후의 봉만. 과거 구간 검증은 3단계(백테스트).
- 기준가는 신호 봉의 종가. 실제로는 다음 날 시가에 들어가므로 결과가 약간 낙관적일 수 있다.
- 벤치마크: 국내 KODEX 200(069500), 미국 SPY. 초과수익 = 종목 − 벤치마크 (하락 신호는 부호 반대).
- 표본이 SAMPLE_MIN 미만이면 통계에 "표본 부족"을 붙인다.

실행: uv run python -m invest.signals   (스캔·채점 후 통계 출력)
"""

import datetime as dt
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors import storage

log = logging.getLogger("invest.signals")

HISTORY_DAYS = 420      # 52주 신고가(직전 250봉) 계산에 필요한 일봉 확보
SCAN_BARS = 5           # 최근 N봉까지 소급 탐지 (맥이 며칠 잠들었어도 놓치지 않게)
ADDED_GRACE_DAYS = 7    # 관심 추가일 N일 전 봉까지는 기록 (추가 당일 아침엔 전날 봉이 최신이라서)
HORIZONS = (5, 20)
SAMPLE_MIN = 30
BENCHMARKS = {"KR": ("069500", "KODEX 200"), "US": ("SPY", "SPY")}
RULES_KEY = "invest_signal_rules"   # 꺼진 규칙 id 목록

# id: (이름, 방향, 설명)
RULES = {
    "golden_20_60": ("골든크로스 20/60", "up", "20일 이동평균이 60일 이동평균을 위로 돌파"),
    "dead_20_60":   ("데드크로스 20/60", "down", "20일 이동평균이 60일 이동평균을 아래로 돌파"),
    "macd_up":      ("MACD 상향 교차", "up", "MACD(12,26)가 시그널(9)을 위로 돌파"),
    "macd_down":    ("MACD 하향 교차", "down", "MACD(12,26)가 시그널(9)을 아래로 돌파"),
    "rsi_up_30":    ("RSI 30 회복", "up", "RSI(14)가 30을 아래에서 위로 돌파 (과매도 탈출)"),
    "rsi_down_70":  ("RSI 70 이탈", "down", "RSI(14)가 70을 위에서 아래로 돌파 (과매수 이탈)"),
    "high_52w":     ("52주 신고가", "up", "종가가 직전 250거래일 최고 종가를 처음 넘어섬"),
}


# ---------- 데이터·지표 ----------

class _History:
    """한 번의 실행 안에서 같은 종목 일봉을 두 번 받지 않도록 캐시."""

    def __init__(self):
        self._cache = {}

    def get(self, symbol: str):
        if symbol not in self._cache:
            import FinanceDataReader as fdr
            start = (dt.date.today() - dt.timedelta(days=HISTORY_DAYS)).isoformat()
            try:
                self._cache[symbol] = fdr.DataReader(symbol, start).dropna(subset=["Close"])
            except Exception as e:
                log.warning("일봉 조회 실패 %s: %s", symbol, e)
                self._cache[symbol] = None
        return self._cache[symbol]


def _indicators(df):
    import pandas as pd
    c = df.Close.astype(float)
    out = pd.DataFrame({"close": c})
    out["ma20"], out["ma60"] = c.rolling(20).mean(), c.rolling(60).mean()
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    out["macd"], out["macd_sig"] = macd, macd.ewm(span=9, adjust=False).mean()
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    out["rsi"] = 100 - 100 / (1 + gain / loss)
    out["high250"] = c.shift(1).rolling(250).max()
    return out


def _cross_up(a_prev, a, b_prev, b) -> bool:
    return a_prev <= b_prev and a > b


def _fires(rule: str, p, r) -> bool:
    """p: 전 봉, r: 이번 봉 (지표 행). 값이 비어 있으면(기간 부족) False."""
    import math

    def ok(*vals):
        return all(v is not None and not math.isnan(v) for v in vals)

    if rule in ("golden_20_60", "dead_20_60"):
        if not ok(p.ma20, p.ma60, r.ma20, r.ma60):
            return False
        return _cross_up(p.ma20, r.ma20, p.ma60, r.ma60) if rule == "golden_20_60" else _cross_up(p.ma60, r.ma60, p.ma20, r.ma20)
    if rule in ("macd_up", "macd_down"):
        if not ok(p.macd, p.macd_sig, r.macd, r.macd_sig):
            return False
        return _cross_up(p.macd, r.macd, p.macd_sig, r.macd_sig) if rule == "macd_up" else _cross_up(p.macd_sig, r.macd_sig, p.macd, r.macd)
    if rule == "rsi_up_30":
        return ok(p.rsi, r.rsi) and p.rsi <= 30 < r.rsi
    if rule == "rsi_down_70":
        return ok(p.rsi, r.rsi) and p.rsi >= 70 > r.rsi
    if rule == "high_52w":
        return ok(p.high250, r.high250) and r.close > r.high250 and not p.close > p.high250
    return False


# ---------- 규칙 on/off ----------

def disabled_rules(conn) -> set[str]:
    raw = storage.get_setting(conn, RULES_KEY)
    return set(json.loads(raw)) if raw else set()


def set_rule_enabled(conn, ref: str, enabled: bool) -> str | None:
    """ref: 규칙 번호(1~) 또는 id. 바꾼 규칙 id, 못 찾으면 None."""
    ids = list(RULES)
    ref = ref.strip()
    rid = ids[int(ref) - 1] if ref.isdigit() and 1 <= int(ref) <= len(ids) else (ref if ref in RULES else None)
    if rid is None:
        rid = next((k for k, v in RULES.items() if v[0].replace(" ", "") == ref.replace(" ", "")), None)
    if rid is None:
        return None
    off = disabled_rules(conn)
    off.discard(rid) if enabled else off.add(rid)
    storage.set_setting(conn, RULES_KEY, json.dumps(sorted(off)))
    return rid


def format_rules(conn) -> str:
    off = disabled_rules(conn)
    lines = [f"{i}. {'🟢' if k not in off else '⚪'} {name} ({'상승' if d == 'up' else '하락'} 예상) — {desc}"
             for i, (k, (name, d, desc)) in enumerate(RULES.items(), 1)]
    return ("🧭 신호 규칙 (측정 대상 — 매매 추천 아님)\n" + "\n".join(lines)
            + "\n\n끄기/켜기: 「신호 끄기 : 3」 「신호 켜기 : 3」")


# ---------- 스캔·채점 ----------

def scan(conn, items: list[dict], hist: _History) -> list[dict]:
    """관심 종목의 최근 SCAN_BARS봉에서 새 신호를 찾아 기록. 새로 기록된 신호 목록을 반환."""
    off = disabled_rules(conn)
    now = dt.datetime.now().isoformat(timespec="seconds")
    new = []
    for it in items:
        df = hist.get(it["code"])
        if df is None or len(df) < 3:
            continue
        ind = _indicators(df)
        added = dt.date.fromisoformat(it.get("added") or dt.date.today().isoformat())
        floor = added - dt.timedelta(days=ADDED_GRACE_DAYS)
        start = max(1, len(ind) - SCAN_BARS)
        for i in range(start, len(ind)):
            d = ind.index[i].date()
            if d < floor:
                continue
            p, r = ind.iloc[i - 1], ind.iloc[i]
            for rule, (name, direction, _) in RULES.items():
                if rule in off or not _fires(rule, p, r):
                    continue
                cur = conn.execute(
                    """INSERT OR IGNORE INTO signals (rule, direction, code, name, market, signal_date, price, detected_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (rule, direction, it["code"], it["name"], it["market"], d.isoformat(), float(r.close), now),
                )
                if cur.rowcount:
                    new.append({"rule": rule, "name": it["name"], "code": it["code"], "date": d, "price": float(r.close)})
    conn.commit()
    return new


def _ret_after(df, signal_date: str, h: int):
    """신호 봉 이후 h번째 봉의 수익률(%)과 그 봉 날짜. 아직 봉이 부족하면 (None, None)."""
    import pandas as pd
    idx = df.index.searchsorted(pd.Timestamp(signal_date))
    if idx >= len(df) or df.index[idx].date().isoformat() != signal_date or idx + h >= len(df):
        return None, None
    base, later = float(df.Close.iloc[idx]), float(df.Close.iloc[idx + h])
    return (later / base - 1) * 100, df.index[idx + h]


def _bench_ret(bdf, start_date: str, end_ts):
    """벤치마크의 같은 기간 수익률 (각 날짜 이전 가장 가까운 종가 기준)."""
    import pandas as pd
    if bdf is None or bdf.empty:
        return None
    a = bdf.Close[bdf.index <= pd.Timestamp(start_date)]
    b = bdf.Close[bdf.index <= end_ts]
    if a.empty or b.empty:
        return None
    return (float(b.iloc[-1]) / float(a.iloc[-1]) - 1) * 100


def evaluate(conn, hist: _History) -> list[dict]:
    """결과가 비어 있는 신호 중 기간이 찬 것을 채점. 새로 확정된 (신호, 기간) 목록 반환."""
    rows = conn.execute("SELECT * FROM signals WHERE ret_5d IS NULL OR ret_20d IS NULL").fetchall()
    done = []
    for s in rows:
        df = hist.get(s["code"])
        if df is None:
            continue
        bdf = hist.get(BENCHMARKS[s["market"]][0])
        for h in HORIZONS:
            if s[f"ret_{h}d"] is not None:
                continue
            ret, end_ts = _ret_after(df, s["signal_date"], h)
            if ret is None:
                continue
            bench = _bench_ret(bdf, s["signal_date"], end_ts)
            conn.execute(f"UPDATE signals SET ret_{h}d=?, bench_{h}d=? WHERE id=?", (ret, bench, s["id"]))
            done.append({"rule": s["rule"], "direction": s["direction"], "name": s["name"], "h": h, "ret": ret, "bench": bench})
    conn.commit()
    return done


def run(conn, items: list[dict]) -> tuple[list[dict], list[dict]]:
    hist = _History()
    return scan(conn, items, hist), evaluate(conn, hist)


# ---------- 통계·표시 ----------

def _hit(direction: str, ret: float) -> bool:
    return ret > 0 if direction == "up" else ret < 0


def _excess(direction: str, ret: float, bench: float | None) -> float | None:
    if bench is None:
        return None
    return ret - bench if direction == "up" else bench - ret


def stats(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM signals").fetchall()
    out = []
    for rule, (name, direction, _) in RULES.items():
        rs = [r for r in rows if r["rule"] == rule]
        st = {"rule": rule, "name": name, "direction": direction, "n": len(rs)}
        for h in HORIZONS:
            ev = [r for r in rs if r[f"ret_{h}d"] is not None]
            ex = [e for r in ev if (e := _excess(direction, r[f"ret_{h}d"], r[f"bench_{h}d"])) is not None]
            st[h] = {
                "n": len(ev),
                "hit": sum(_hit(direction, r[f"ret_{h}d"]) for r in ev) / len(ev) * 100 if ev else None,
                "avg": sum(r[f"ret_{h}d"] for r in ev) / len(ev) if ev else None,
                "excess": sum(ex) / len(ex) if ex else None,
            }
        out.append(st)
    return out


def format_stats(conn) -> str:
    total = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    if not total:
        return ("📒 신호 기록부 — 아직 기록된 신호가 없습니다.\n"
                "관심 종목(「관심 추가 : …」)에서 규칙 신호가 나면 투자 브리핑 때 자동 기록되고, "
                "5·20거래일 뒤 결과가 채점됩니다.\n\n「신호 규칙」으로 측정 중인 규칙을 볼 수 있어요.")
    lines = [f"📒 신호 기록부 — 총 {total}건 (포워드 테스트, 매매 추천 아님)",
             "적중 = 예상 방향으로 움직임 · 초과 = 벤치마크 대비 (하락 신호는 덜 오르거나 더 빠지면 +)", ""]
    for st in stats(conn):
        if not st["n"]:
            continue
        lines.append(f"▪️ {st['name']} ({'상승' if st['direction'] == 'up' else '하락'} 예상) — {st['n']}건")
        for h in HORIZONS:
            e = st[h]
            if not e["n"]:
                lines.append(f"   {h}일: 채점 대기")
                continue
            ex = f" · 초과 {e['excess']:+.2f}%p" if e["excess"] is not None else ""
            warn = " ⚠️표본 부족" if e["n"] < SAMPLE_MIN else ""
            lines.append(f"   {h}일: {e['n']}건 적중 {e['hit']:.0f}% · 평균 {e['avg']:+.2f}%{ex}{warn}")
    lines += ["", f"표본 {SAMPLE_MIN}건 미만은 우연과 구분하기 어렵습니다. 기준가는 신호 봉 종가라 실제보다 약간 낙관적입니다."]
    return "\n".join(lines)


def format_recent(conn, n: int = 15) -> str:
    rows = conn.execute("SELECT * FROM signals ORDER BY signal_date DESC, id DESC LIMIT ?", (n,)).fetchall()
    if not rows:
        return "기록된 신호가 없습니다."
    lines = [f"🗂 최근 신호 {len(rows)}건"]
    for r in rows:
        res = " · ".join(f"{h}일 {r[f'ret_{h}d']:+.1f}%" for h in HORIZONS if r[f"ret_{h}d"] is not None) or "채점 대기"
        lines.append(f"• {r['signal_date'][5:]} {r['name']} — {RULES.get(r['rule'], (r['rule'],))[0]} [{res}]")
    return "\n".join(lines)


def format_brief_section(new: list[dict], done: list[dict]) -> list[str]:
    """투자 브리핑 첫 메시지에 붙일 줄 (평문 — 호출 측에서 HTML 이스케이프)."""
    lines = []
    if new:
        lines += ["", "🧭 새 신호 (기록만 — 매매 신호 아님)"]
        lines += [f"• {s['name']} {RULES[s['rule']][0]} [{s['date']:%m/%d} 종가 기준]" for s in new]
    if done:
        lines += ["", "📏 결과 확정"]
        for d in done:
            b = f" (벤치 {d['bench']:+.1f}%)" if d["bench"] is not None else ""
            mark = "✅" if _hit(d["direction"], d["ret"]) else "❌"
            lines.append(f"• {mark} {d['name']} {RULES[d['rule']][0]} {d['h']}일 {d['ret']:+.1f}%{b}")
    if new or done:
        lines.append("누적 통계: 「신호 통계」")
    return lines


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from invest import brief
    c = storage.connect()
    new, done = run(c, brief.get_watchlist(c))
    print("\n".join(format_brief_section(new, done)) or "새 신호·확정 결과 없음")
    print(format_stats(c))
