"""AI Info Radar 대시보드.

실행: uv run streamlit run dashboard/app.py
"""

import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dashboard import ops  # noqa: E402

DB_PATH = ROOT / "data" / "radar.db"
BLUEPRINT_DIR = ROOT / "blueprints"

PAGE_SIZE = 10

STATUS_LABEL = {
    "new": "미처리",
    "rescore": "재평가 대기",
    "processed": "처리됨",
    "briefed": "브리핑됨",
    "approved": "구현 승인",
    "skipped": "스킵",
}

st.set_page_config(page_title="AI Info Radar", layout="wide")

CYCLE_INTERVAL_MIN = 30   # launchd StartInterval 1800
STALE_AFTER_MIN = 90      # 마지막 사이클이 이보다 오래되면 경고
TASK_LABEL = {"score": "채점 (haiku)", "blueprint": "블루프린트 (sonnet)", "topic": "주제 확장 (haiku)"}
STATUS_ICON = {"정상": "✅ 정상", "에러": "⚠️ 에러", "중단": "⛔ 중단", "진행 중": "⏳ 진행 중"}
MODE_COLORS = ["#2a78d6", "#eb6834"]  # 파이프라인, 대화형 (고정 순서)


@st.cache_data(ttl=60)
def load_cycles() -> pd.DataFrame:
    return pd.DataFrame(ops.parse_cycles())


@st.cache_data(max_entries=2000)
def _session_rows(path: str, mtime: float, size: int) -> list[dict]:
    """파일별 캐시: 바뀐 세션 파일만 다시 읽음."""
    return ops.parse_session_file(Path(path))


@st.cache_data(ttl=120)
def load_sessions() -> pd.DataFrame:
    rows = []
    for f in ops.session_files():
        st_ = f.stat()
        rows += _session_rows(str(f), st_.st_mtime, st_.st_size)
    rows += ops.usage_rows_from_calls(ops.load_llm_calls())
    return pd.DataFrame(rows)


@st.cache_data(ttl=60)
def load_llm_calls() -> pd.DataFrame:
    return pd.DataFrame(ops.load_llm_calls())


@st.cache_data(ttl=60)
def load_items() -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(
            "SELECT id, score, kind, category, status, source, COALESCE(title_ko, title) AS title, summary, easy, use_cases, content, url, "
            "blueprint_path, published_at, collected_at, topic FROM items",
            conn,
        )


@st.cache_data(ttl=60)
def load_current_topic() -> str | None:
    with sqlite3.connect(DB_PATH) as conn:
        try:
            row = conn.execute("SELECT value FROM settings WHERE key='topic'").fetchone()
        except sqlite3.OperationalError:
            return None
    return json.loads(row[0])["topic"] if row else None


def score_badge(score) -> str:
    if pd.isna(score):
        return "⬜ 미평가"
    score = int(score)
    icon = "🟢" if score >= 70 else "🟡" if score >= 40 else "🔴"
    return f"{icon} {score}점"


def render_card(row) -> None:
    with st.container(border=True):
        top1, top2 = st.columns([3, 1])
        with top1:
            st.markdown(f"### {row.title or '(제목 없음)'}")
        with top2:
            st.markdown(
                f"<div style='text-align:right; font-size:1.1em'>{score_badge(row.score)}</div>",
                unsafe_allow_html=True,
            )

        meta = " · ".join(filter(None, [
            {"구현": "🛠 구현", "뉴스": "📰 뉴스"}.get(row.kind),
            row.category,
            row.source,
            STATUS_LABEL.get(row.status, row.status),
            (row.published_at or "")[:10],
        ]))
        st.caption(meta)

        if isinstance(row.easy, str) and row.easy:
            st.info(f"💬 {row.easy}")
        if row.summary and isinstance(row.summary, str):
            for line in row.summary.split("\n"):
                if line.strip():
                    st.markdown(f"- {line.strip()}")
        if isinstance(row.use_cases, str) and row.use_cases.strip():
            st.markdown("**💡 이걸로 할 수 있는 것**")
            for line in row.use_cases.split("\n"):
                if line.strip():
                    st.markdown(f"- {line.strip()}")

        st.markdown(f"[원본 링크 열기]({row.url})")

        if isinstance(row.content, str) and row.content.strip():
            with st.expander("원문 보기"):
                st.text(row.content[:3000])

        if isinstance(row.blueprint_path, str) and row.blueprint_path:
            bp = ROOT / row.blueprint_path
            if bp.exists():
                with st.expander("📋 구현 블루프린트"):
                    st.markdown(bp.read_text())


st.title("AI Info Radar")

if not DB_PATH.exists():
    st.warning("data/radar.db가 없습니다. 먼저 수집을 실행하세요: uv run python -m collectors.run")
    st.stop()

df = load_items()
current_topic = load_current_topic()
st.caption(
    f"현재 주제: **{current_topic}**" if current_topic
    else "현재 주제: (기본) AI 기반 업무 효율화·자동화 — 텔레그램에 「주제 설정 : …」을 보내 변경"
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("전체 수집", len(df))
c2.metric("처리 완료", int((df["status"] != "new").sum()))
c3.metric("70점 이상", int((df["score"] >= 70).sum()))
c4.metric("블루프린트", int(df["blueprint_path"].notna().sum()))

tab_feed, tab_table, tab_blueprints, tab_ops = st.tabs(["피드", "테이블", "블루프린트", "운영 현황"])

with tab_feed:
    with st.sidebar:
        st.header("필터")
        topics = st.multiselect("주제", sorted(df["topic"].dropna().unique()))
        sources = st.multiselect("소스", sorted(df["source"].unique()))
        statuses = st.multiselect(
            "상태", sorted(df["status"].unique()), format_func=lambda s: STATUS_LABEL.get(s, s)
        )
        categories = st.multiselect("카테고리", sorted(df["category"].dropna().unique()))
        min_score = st.slider("최소 점수", 0, 100, 0)
        include_unscored = st.checkbox("미평가 포함", value=(min_score == 0))
        sort_key = st.radio("정렬", ["점수순", "최신순"], horizontal=True)

    view = df.copy()
    if topics:
        view = view[view["topic"].isin(topics)]
    if sources:
        view = view[view["source"].isin(sources)]
    if statuses:
        view = view[view["status"].isin(statuses)]
    if categories:
        view = view[view["category"].isin(categories)]
    scored_mask = view["score"].notna() & (view["score"] >= min_score)
    view = view[scored_mask | (view["score"].isna() if include_unscored else False)]

    if sort_key == "점수순":
        view = view.sort_values("score", ascending=False, na_position="last")
    else:
        view = view.assign(_date=view["published_at"].fillna(view["collected_at"]))
        view = view.sort_values("_date", ascending=False, na_position="last")

    total_pages = max(1, -(-len(view) // PAGE_SIZE))
    colp1, colp2 = st.columns([1, 4])
    with colp1:
        page = st.number_input("페이지", min_value=1, max_value=total_pages, value=1)
    with colp2:
        st.caption(f"총 {len(view)}건 / {total_pages}페이지")

    start = (page - 1) * PAGE_SIZE
    for row in view.iloc[start:start + PAGE_SIZE].itertuples():
        render_card(row)

with tab_table:
    st.dataframe(
        df.sort_values("score", ascending=False, na_position="last")[
            ["id", "score", "category", "status", "source", "title", "summary", "url"]
        ],
        use_container_width=True,
        hide_index=True,
        column_config={
            "url": st.column_config.LinkColumn("링크"),
            "summary": st.column_config.TextColumn("요약", width="large"),
        },
    )

with tab_blueprints:
    files = sorted(BLUEPRINT_DIR.glob("*.md"), reverse=True) if BLUEPRINT_DIR.exists() else []
    if not files:
        st.info("생성된 블루프린트가 없습니다.")
    else:
        selected = st.selectbox("블루프린트 선택", files, format_func=lambda p: p.name)
        st.markdown(selected.read_text())

with tab_ops:
    cycles = load_cycles()
    sessions = load_sessions()
    now = datetime.now()

    # --- 헤드라인 ---
    c1, c2, c3, c4 = st.columns(4)
    if cycles.empty:
        c1.metric("마지막 사이클", "기록 없음")
    else:
        last = cycles.iloc[-1]
        ago = int((now - last["start"]).total_seconds() // 60)
        c1.metric("마지막 사이클", f"{ago}분 전")
        c1.caption(f"{STATUS_ICON.get(last['status'], last['status'])} · {last['start']:%m-%d %H:%M} 시작")
        if ago > STALE_AFTER_MIN:
            st.error(f"마지막 사이클이 {ago}분 전입니다 ({CYCLE_INTERVAL_MIN}분 주기). 맥이 잠들었거나 launchd 작업이 멈췄을 수 있어요.")
        day = cycles[cycles["start"] >= now - timedelta(hours=24)]
        n_err = int((day["status"] != "정상").sum())
        c2.metric("최근 24시간 사이클", f"{len(day)}회")
        c2.caption(f"⚠️ 문제 {n_err}회" if n_err else "✅ 모두 정상")

    if not sessions.empty:
        today = now.strftime("%Y-%m-%d")
        week = (now - timedelta(days=6)).strftime("%Y-%m-%d")
        # st.caption은 $…$를 수식으로 해석하므로 \$로 이스케이프
        by_mode = lambda d: " · ".join(f"{m} \\${v:,.2f}" for m, v in d.groupby("mode")["cost_usd"].sum().sort_index(ascending=False).items())
        t = sessions[sessions["date"] == today]
        w = sessions[sessions["date"] >= week]
        c3.metric("오늘 추정 비용", f"${t['cost_usd'].sum():,.2f}")
        c3.caption(by_mode(t))
        c4.metric("최근 7일 추정 비용", f"${w['cost_usd'].sum():,.2f}")
        c4.caption(by_mode(w))
    st.caption("비용은 Claude Code 세션 기록의 토큰을 API 정가로 환산한 추정치입니다. 구독 요금제의 실제 청구액과 다릅니다.")

    # --- 사이클 실행 기록 ---
    st.subheader("사이클 실행 기록")
    if cycles.empty:
        st.info("logs/launchd.cycle.log 가 없습니다.")
    else:
        view = cycles.iloc[::-1].head(60).assign(
            상태=lambda d: d["status"].map(lambda x: STATUS_ICON.get(x, x)),
            시작=lambda d: d["start"].dt.strftime("%m-%d %H:%M"),
            에러=lambda d: d["errors"].map(lambda e: " / ".join(e[:3]) + (f" 외 {len(e) - 3}건" if len(e) > 3 else "")),
        )
        st.dataframe(
            view[["시작", "상태", "duration_s", "new", "scored", "blueprints", "publish", "warnings", "에러"]],
            hide_index=True, use_container_width=True,
            column_config={
                "duration_s": st.column_config.NumberColumn("소요(초)", format="%d"),
                "new": st.column_config.NumberColumn("신규", format="%d"),
                "scored": st.column_config.NumberColumn("채점", format="%d"),
                "blueprints": st.column_config.NumberColumn("블루프린트", format="%d"),
                "publish": "배포", "warnings": st.column_config.NumberColumn("경고", format="%d"),
                "에러": st.column_config.TextColumn("에러", width="large"),
            },
        )

    # --- 사용량·비용 ---
    st.subheader("토큰 사용량 · 추정 비용")
    if sessions.empty:
        st.info("~/.claude/projects 에 세션 기록이 없습니다.")
    else:
        period = st.radio("기간", ["최근 7일", "최근 30일", "전체"], horizontal=True, key="ops_period")
        days = {"최근 7일": 7, "최근 30일": 30}.get(period)
        sv = sessions if days is None else sessions[sessions["date"] >= (now - timedelta(days=days - 1)).strftime("%Y-%m-%d")]

        # 모드별 열로 펼쳐 색을 고정 순서로 지정 (파이프라인=1번, 대화형=2번 색)
        modes = ["파이프라인", "대화형"]
        daily = sv.pivot_table(index="date", columns="mode", values="cost_usd", aggfunc="sum", fill_value=0)
        daily = daily.reindex(columns=modes, fill_value=0).reset_index()
        st.markdown("**일별 추정 비용 (USD)**")
        st.bar_chart(daily, x="date", y=modes, color=MODE_COLORS, x_label="날짜", y_label="추정 비용 (USD)", stack=True)

        tok = lambda d: d[["input_tokens", "cache_read", "cache_write_5m", "cache_write_1h"]].sum(axis=1)
        st.markdown("**프로젝트별**")
        proj = (sv.assign(입력=tok(sv))
                  .groupby(["project", "mode"], as_index=False)
                  .agg(세션=("session", "nunique"), 입력=("입력", "sum"), 출력=("output_tokens", "sum"), 비용=("cost_usd", "sum"))
                  .sort_values("비용", ascending=False))
        st.dataframe(proj.rename(columns={"project": "프로젝트", "mode": "구분"}), hide_index=True, use_container_width=True,
                     column_config={"입력": st.column_config.NumberColumn("입력 토큰", format="%d"),
                                    "출력": st.column_config.NumberColumn("출력 토큰", format="%d"),
                                    "비용": st.column_config.NumberColumn("추정 비용", format="$%.2f")})
        st.markdown("**파이프라인 작업별 (claude -p 호출)**")
        pipe = sv[sv["mode"] == "파이프라인"]
        if pipe.empty:
            st.caption("이 기간에 파이프라인 호출이 없습니다.")
        else:
            per_call = (pipe.assign(입력=tok(pipe), task=pipe["task"].map(lambda t: TASK_LABEL.get(t, "기타")))
                            .groupby(["task", "session"], as_index=False)
                            .agg(입력=("입력", "sum"), 비용=("cost_usd", "sum")))
            tasks = (per_call.groupby("task", as_index=False)
                             .agg(호출=("session", "count"), 호출당_입력=("입력", "mean"), 호출당_비용=("비용", "mean"), 합계=("비용", "sum"))
                             .sort_values("합계", ascending=False))
            st.dataframe(tasks.rename(columns={"task": "작업"}), hide_index=True, use_container_width=True,
                         column_config={"호출당_입력": st.column_config.NumberColumn("호출당 입력 토큰", format="%d"),
                                        "호출당_비용": st.column_config.NumberColumn("호출당 비용", format="$%.3f"),
                                        "합계": st.column_config.NumberColumn("합계", format="$%.2f")})
            st.caption("2026-09-27 이전 호출은 Claude Code 기본 시스템 프롬프트·도구 정의(약 3만 토큰)가 붙어 있었고, "
                       "이후로는 도구를 끈 가벼운 호출이라 호출당 입력이 크게 줄어듭니다.")

    # --- 파이프라인 LLM 호출 기록 (data/llm_usage.jsonl) ---
    calls = load_llm_calls()
    st.subheader("최근 파이프라인 LLM 호출")
    if calls.empty:
        st.caption("아직 기록이 없습니다. 다음 사이클부터 data/llm_usage.jsonl 에 쌓입니다.")
    else:
        fails = calls[~calls["ok"]]
        if not fails.empty:
            st.warning(f"실패한 호출 {len(fails)}건 — 최근: {fails.iloc[-1].get('error', '')}")
        cols = [c for c in ["ts", "task", "model", "ok", "duration_ms", "cache_read", "output_tokens", "cost_usd", "error"] if c in calls]
        st.dataframe(calls.iloc[::-1].head(50)[cols], hide_index=True, use_container_width=True,
                     column_config={"ts": "시각", "task": "작업", "model": "모델", "ok": "성공",
                                    "duration_ms": st.column_config.NumberColumn("소요(ms)", format="%d"),
                                    "cache_read": st.column_config.NumberColumn("캐시 읽기", format="%d"),
                                    "output_tokens": st.column_config.NumberColumn("출력", format="%d"),
                                    "cost_usd": st.column_config.NumberColumn("비용", format="$%.4f")})
