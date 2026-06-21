"""Employee 360 — HRIS worked example.

A Cortex RAG Assistant tab (unchanged generic module) plus People dashboards
built on the generated demo data. Every identity value comes from app_config.py.
"""
import altair as alt
import pandas as pd
import streamlit as st

import app_config as cfg
from _core import session, q
import rag_chat

FQ = f"{cfg.DATABASE}.{cfg.SCHEMA}"

st.title(f"{cfg.APP_ICON} {cfg.APP_TITLE}")

tab_assistant, tab_workforce, tab_attrition, tab_sentiment, tab_time = st.tabs(
    ["💬 Assistant", "👥 Workforce", "📈 Joiners & Attrition", "😊 Sentiment", "⏱️ Time & Training"]
)

with tab_assistant:
    rag_chat.render(session, cfg)

with tab_workforce:
    st.subheader("Workforce")
    wf = q(f"""
        SELECT COALESCE(ef.EMPLOYMENT_TYPE, 'Full-time') AS TYPE, COUNT(*) AS CNT
        FROM {FQ}.EMPLOYEES e
        LEFT JOIN {FQ}.EMPLOYEE_FIELDS ef ON e.EMPLOYEE_ID = ef.EMPLOYEE_ID
        WHERE e.TERMINATION_DATE IS NULL OR e.TERMINATION_DATE > CURRENT_DATE()
        GROUP BY 1
    """)
    by_type = dict(zip(wf["TYPE"], wf["CNT"]))
    total = int(sum(by_type.values()))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active Headcount", total)
    c2.metric("Full-time", int(by_type.get("Full-time", 0)))
    c3.metric("Contractor", int(by_type.get("Contractor", 0)))
    c4.metric("Managed Workforce", int(by_type.get("Managed Workforce", 0)))

    st.markdown("##### Headcount by Department")
    dept = q(f"""
        SELECT e.DEPARTMENT, COUNT(*) AS HEADCOUNT
        FROM {FQ}.EMPLOYEES e
        WHERE e.TERMINATION_DATE IS NULL OR e.TERMINATION_DATE > CURRENT_DATE()
        GROUP BY 1 ORDER BY 2 DESC
    """)
    if len(dept):
        st.altair_chart(
            alt.Chart(dept).mark_bar().encode(
                x=alt.X("DEPARTMENT:N", sort="-y"), y="HEADCOUNT:Q",
                tooltip=["DEPARTMENT", "HEADCOUNT"]).properties(height=300),
            use_container_width=True,
        )

with tab_attrition:
    st.subheader("Joiners vs Leavers (last 12 months)")
    jl = q(f"""
        WITH months AS (
            SELECT DATEADD('month', -seq, DATE_TRUNC('MONTH', CURRENT_DATE()))::DATE AS M
            FROM (SELECT ROW_NUMBER() OVER (ORDER BY SEQ4()) - 1 AS seq
                  FROM TABLE(GENERATOR(ROWCOUNT => 12)))
        ),
        joiners AS (
            SELECT DATE_TRUNC('MONTH', HIRE_DATE)::DATE AS M, COUNT(*) AS JOINERS
            FROM {FQ}.EMPLOYEES WHERE HIRE_DATE >= DATEADD('month', -12, CURRENT_DATE()) GROUP BY 1
        ),
        leavers AS (
            SELECT DATE_TRUNC('MONTH', TERMINATION_DATE)::DATE AS M, COUNT(*) AS LEAVERS
            FROM {FQ}.EMPLOYEES
            WHERE TERMINATION_DATE IS NOT NULL AND TERMINATION_DATE >= DATEADD('month', -12, CURRENT_DATE())
            GROUP BY 1
        )
        SELECT m.M AS MONTH, COALESCE(j.JOINERS, 0) AS JOINERS, COALESCE(l.LEAVERS, 0) AS LEAVERS
        FROM months m LEFT JOIN joiners j ON m.M = j.M LEFT JOIN leavers l ON m.M = l.M
        ORDER BY m.M
    """)
    if len(jl):
        c1, c2 = st.columns(2)
        c1.metric("Joiners (12 mo)", int(jl["JOINERS"].sum()))
        c2.metric("Leavers (12 mo)", int(jl["LEAVERS"].sum()))
        chart_df = jl.copy()
        chart_df["MONTH"] = pd.to_datetime(chart_df["MONTH"])
        st.bar_chart(chart_df.set_index("MONTH")[["JOINERS", "LEAVERS"]], color=["#2196F3", "#F44336"])

with tab_sentiment:
    st.subheader("Sentiment & Performance")
    sent = q(f"""
        SELECT DATE_TRUNC('MONTH', REVIEW_DATE)::DATE AS MONTH,
               ROUND(AVG(SENTIMENT_SCORE) * 100, 1) AS AVG_SENTIMENT
        FROM {FQ}.PERFORMANCE_REVIEWS
        WHERE REVIEW_DATE >= DATEADD('month', -12, CURRENT_DATE())
        GROUP BY 1 ORDER BY 1
    """)
    ytd = q(f"""
        SELECT ROUND(AVG(SENTIMENT_SCORE) * 100, 1) AS S
        FROM {FQ}.PERFORMANCE_REVIEWS WHERE YEAR(REVIEW_DATE) = YEAR(CURRENT_DATE())
    """)
    if len(ytd) and pd.notna(ytd.iloc[0]["S"]):
        st.metric("YTD Sentiment Score", f"{ytd.iloc[0]['S']:.1f}%")
    if len(sent):
        s = sent.copy()
        s["MONTH"] = pd.to_datetime(s["MONTH"])
        st.line_chart(s.set_index("MONTH")["AVG_SENTIMENT"])

    st.markdown("##### Rating distribution")
    rating = q(f"SELECT RATING, COUNT(*) AS CNT FROM {FQ}.PERFORMANCE_REVIEWS GROUP BY 1 ORDER BY 1")
    if len(rating):
        st.bar_chart(rating.set_index("RATING")["CNT"])

with tab_time:
    st.subheader("Internal Training % of Logged Hours")
    tr = q(f"""
        SELECT DATE_TRUNC('MONTH', te.SPENT_DATE)::DATE AS MONTH,
               ROUND(SUM(CASE WHEN t.TASK_NAME IN ('Training', 'Meeting') THEN te.HOURS ELSE 0 END)
                     * 100.0 / NULLIF(SUM(te.HOURS), 0), 2) AS TRAINING_PCT
        FROM {FQ}.TIME_ENTRIES te JOIN {FQ}.TASKS t ON te.TASK_ID = t.TASK_ID
        WHERE te.SPENT_DATE >= DATEADD('month', -12, CURRENT_DATE())
        GROUP BY 1 ORDER BY 1
    """)
    if len(tr):
        t = tr.copy()
        t["MONTH"] = pd.to_datetime(t["MONTH"])
        st.bar_chart(t.set_index("MONTH")["TRAINING_PCT"])

    st.markdown("##### Billable vs non-billable hours (last 3 months)")
    bill = q(f"""
        SELECT CASE WHEN IS_BILLABLE THEN 'Billable' ELSE 'Non-billable' END AS KIND,
               ROUND(SUM(HOURS), 0) AS HOURS
        FROM {FQ}.TIME_ENTRIES
        WHERE SPENT_DATE >= DATEADD('month', -3, CURRENT_DATE())
        GROUP BY 1
    """)
    if len(bill):
        st.bar_chart(bill.set_index("KIND")["HOURS"])
