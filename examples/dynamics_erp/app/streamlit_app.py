"""Northwind ERP — Microsoft Dynamics worked example.

A Cortex RAG Assistant tab (unchanged generic module) plus finance/operations
dashboards built on the generated demo data. Identity comes from app_config.py.
"""
import altair as alt
import pandas as pd
import streamlit as st

import app_config as cfg
from _core import session, q
import rag_chat

FQ = f"{cfg.DATABASE}.{cfg.SCHEMA}"

st.title(f"{cfg.APP_ICON} {cfg.APP_TITLE}")

tab_assistant, tab_revenue, tab_customers, tab_ar, tab_ops = st.tabs(
    ["💬 Assistant", "💰 Revenue", "🏆 Customers", "📅 AR Aging", "📦 Orders & Inventory"]
)

with tab_assistant:
    rag_chat.render(session, cfg)

with tab_revenue:
    st.subheader("Revenue")
    tot = q(f"""
        SELECT ROUND(SUM(TOTAL_AMOUNT), 0) AS YTD, COUNT(*) AS N
        FROM {FQ}.INVOICES WHERE YEAR(INVOICE_DATE) = YEAR(CURRENT_DATE())
    """)
    if len(tot):
        c1, c2 = st.columns(2)
        ytd = tot.iloc[0]["YTD"]
        c1.metric("YTD Invoiced", f"${ytd:,.0f}" if pd.notna(ytd) else "$0")
        c2.metric("YTD Invoices", int(tot.iloc[0]["N"]))
    rev = q(f"""
        SELECT DATE_TRUNC('MONTH', INVOICE_DATE)::DATE AS MONTH, ROUND(SUM(TOTAL_AMOUNT), 0) AS REVENUE
        FROM {FQ}.INVOICES WHERE INVOICE_DATE >= DATEADD('month', -12, CURRENT_DATE())
        GROUP BY 1 ORDER BY 1
    """)
    if len(rev):
        r = rev.copy()
        r["MONTH"] = pd.to_datetime(r["MONTH"])
        st.bar_chart(r.set_index("MONTH")["REVENUE"])

with tab_customers:
    st.subheader("Top Customers by Invoiced Amount")
    top = q(f"""
        SELECT c.DISPLAY_NAME AS CUSTOMER, ROUND(SUM(i.TOTAL_AMOUNT), 0) AS INVOICED
        FROM {FQ}.INVOICES i JOIN {FQ}.CUSTOMERS c ON i.CUSTOMER_ID = c.CUSTOMER_ID
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10
    """)
    if len(top):
        st.altair_chart(
            alt.Chart(top).mark_bar().encode(
                x=alt.X("INVOICED:Q", title="Invoiced ($)"),
                y=alt.Y("CUSTOMER:N", sort="-x"),
                tooltip=["CUSTOMER", "INVOICED"]).properties(height=320),
            use_container_width=True,
        )

with tab_ar:
    st.subheader("Accounts Receivable Aging")
    aging = q(f"""
        SELECT CASE
                 WHEN DATEDIFF('day', DUE_DATE, CURRENT_DATE()) <= 0 THEN '0 Current'
                 WHEN DATEDIFF('day', DUE_DATE, CURRENT_DATE()) <= 30 THEN '1-30 days'
                 WHEN DATEDIFF('day', DUE_DATE, CURRENT_DATE()) <= 60 THEN '31-60 days'
                 ELSE '60+ days' END AS BUCKET,
               ROUND(SUM(TOTAL_AMOUNT), 0) AS OUTSTANDING, COUNT(*) AS INVOICES
        FROM {FQ}.INVOICES WHERE STATUS IN ('Open', 'Overdue')
        GROUP BY 1 ORDER BY 1
    """)
    if len(aging):
        c1, c2 = st.columns(2)
        c1.metric("Open / Overdue Invoices", int(aging["INVOICES"].sum()))
        c2.metric("Total Outstanding", f"${aging['OUTSTANDING'].sum():,.0f}")
        st.bar_chart(aging.set_index("BUCKET")["OUTSTANDING"])
    else:
        st.info("No open or overdue invoices in the current data.")

with tab_ops:
    st.subheader("Orders by Status")
    orders = q(f"SELECT STATUS, COUNT(*) AS ORDERS FROM {FQ}.SALES_ORDERS GROUP BY 1 ORDER BY 2 DESC")
    if len(orders):
        st.bar_chart(orders.set_index("STATUS")["ORDERS"])

    st.markdown("##### Lowest inventory items (reorder candidates)")
    low = q(f"""
        SELECT DISPLAY_NAME AS ITEM, CATEGORY, INVENTORY, ROUND(UNIT_PRICE, 0) AS UNIT_PRICE
        FROM {FQ}.PRODUCTS ORDER BY INVENTORY ASC LIMIT 10
    """)
    if len(low):
        st.dataframe(low, use_container_width=True, hide_index=True)
