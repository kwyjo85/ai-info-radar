"""AI Info Radar 대시보드.

실행: uv run streamlit run dashboard/app.py
"""

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "data" / "radar.db"
BLUEPRINT_DIR = ROOT / "blueprints"

PAGE_SIZE = 10

STATUS_LABEL = {
    "new": "미처리",
    "processed": "처리됨",
    "briefed": "브리핑됨",
    "approved": "구현 승인",
    "skipped": "스킵",
}

st.set_page_config(page_title="AI Info Radar", layout="wide")


@st.cache_data(ttl=60)
def load_items() -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(
            "SELECT id, score, category, status, source, title, summary, content, url, "
            "blueprint_path, published_at, collected_at FROM items",
            conn,
        )


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
            row.category,
            row.source,
            STATUS_LABEL.get(row.status, row.status),
            (row.published_at or "")[:10],
        ]))
        st.caption(meta)

        if row.summary and isinstance(row.summary, str):
            for line in row.summary.split("\n"):
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

c1, c2, c3, c4 = st.columns(4)
c1.metric("전체 수집", len(df))
c2.metric("처리 완료", int((df["status"] != "new").sum()))
c3.metric("70점 이상", int((df["score"] >= 70).sum()))
c4.metric("블루프린트", int(df["blueprint_path"].notna().sum()))

tab_feed, tab_table, tab_blueprints = st.tabs(["피드", "테이블", "블루프린트"])

with tab_feed:
    with st.sidebar:
        st.header("필터")
        sources = st.multiselect("소스", sorted(df["source"].unique()))
        statuses = st.multiselect(
            "상태", sorted(df["status"].unique()), format_func=lambda s: STATUS_LABEL.get(s, s)
        )
        categories = st.multiselect("카테고리", sorted(df["category"].dropna().unique()))
        min_score = st.slider("최소 점수", 0, 100, 0)
        include_unscored = st.checkbox("미평가 포함", value=(min_score == 0))
        sort_key = st.radio("정렬", ["점수순", "최신순"], horizontal=True)

    view = df.copy()
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
