"""Streamlit-in-Snowflake entrypoint.

This generic template ships two tabs:
  • Assistant   — the Cortex RAG chat (rag_chat.render)
  • Data Browser — a domain-agnostic table previewer

Worked examples replace/extend the Data Browser with real dashboards, but the
Assistant tab works unchanged for any data source.
"""
import streamlit as st

import app_config as cfg
from _core import session, q
import rag_chat

st.title(f"{cfg.APP_ICON} {cfg.APP_TITLE}")

tab_assistant, tab_data = st.tabs(["💬 Assistant", "📊 Data Browser"])

with tab_assistant:
    rag_chat.render(session, cfg)

with tab_data:
    st.caption("Generic table browser — replace with your domain dashboards.")
    tables = q(
        f"SELECT TABLE_NAME, ROW_COUNT FROM {cfg.DATABASE}.INFORMATION_SCHEMA.TABLES "
        f"WHERE TABLE_SCHEMA = '{cfg.SCHEMA}' AND TABLE_TYPE = 'BASE TABLE' "
        f"ORDER BY TABLE_NAME"
    )
    if len(tables) == 0:
        st.info("No tables found — run the deploy scripts first.")
    else:
        pick = st.selectbox("Table", tables["TABLE_NAME"].tolist())
        st.dataframe(
            q(f"SELECT * FROM {cfg.DATABASE}.{cfg.SCHEMA}.{pick} LIMIT 200"),
            use_container_width=True,
        )
