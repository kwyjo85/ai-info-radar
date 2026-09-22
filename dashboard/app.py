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

st.set_page_config(page_title="AI Info Radar", layout="wide")


@st.cache_data(ttl=60)
def load_items() -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(
            "SELECT id, score, category, status, source, title, summary, url, "
            "blueprint_path, published_at, collected_at FROM items",
            conn,
        )


st.title("AI Info Radar")

if not DB_PATH.exists():
    st.warning("data/radar.db가 없습니다. 먼저 수집을 실행하세요: uv run python -m collectors.run")
    st.stop()

df = load_items()

# 상단 지표
c1, c2, c3, c4 = st.columns(4)
c1.metric("전체 수집", len(df))
c2.metric("처리 완료", int((df["status"] != "new").sum()))
c3.metric("70점 이상", int((df["score"] >= 70).sum()))
c4.metric("블루프린트", int(df["blueprint_path"].notna().sum()))

tab_items, tab_blueprints = st.tabs(["수집 항목", "블루프린트"])

with tab_items:
    f1, f2, f3, f4 = st.columns(4)
    sources = f1.multiselect("소스", sorted(df["source"].unique()))
    statuses = f2.multiselect("상태", sorted(df["status"].unique()))
    categories = f3.multiselect("카테고리", sorted(df["category"].dropna().unique()))
    min_score = f4.slider("최소 점수", 0, 100, 0)

    view = df.copy()
    if sources:
        view = view[view["source"].isin(sources)]
    if statuses:
        view = view[view["status"].isin(statuses)]
    if categories:
        view = view[view["category"].isin(categories)]
    if min_score:
        view = view[view["score"].fillna(-1) >= min_score]

    view = view.sort_values(["score"], ascending=False, na_position="last")
    st.dataframe(
        view[["id", "score", "category", "status", "source", "title", "summary", "url"]],
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
