import streamlit as st
import pandas as pd
import json
from snowflake.snowpark.context import get_active_session
from datetime import date, timedelta

st.set_page_config(page_title="Employee 360 Dashboard", page_icon="\U0001F465", layout="wide")
session = get_active_session()
DB = "DEMO_EMPLOYEE_APP"
SCH = "GOLD"        # dashboard reads the curated GOLD presentation layer (Bronze->Silver->Gold medallion output)
APP_SCH = "PUBLIC"  # app-managed runtime tables (chat sessions/messages) + the Cortex Search service live in PUBLIC

@st.cache_data(ttl=300)
def q(sql):
    return session.sql(sql).to_pandas()

employees_df = q(f"SELECT * FROM {DB}.{SCH}.EMPLOYEE_360 ORDER BY LAST_NAME, FIRST_NAME")

st.sidebar.title("\U0001F465 Employee 360")
st.sidebar.markdown("---")
departments = ["All"] + sorted(employees_df["DEPARTMENT"].unique().tolist())
selected_dept = st.sidebar.selectbox("Department", departments)
filtered_df = employees_df if selected_dept == "All" else employees_df[employees_df["DEPARTMENT"] == selected_dept]
employee_options = {f"{r['FIRST_NAME']} {r['LAST_NAME']} ({r['TITLE']})": r['EMPLOYEE_ID'] for _, r in filtered_df.iterrows()}
selected_name = st.sidebar.selectbox("Select Employee", list(employee_options.keys()))
eid = employee_options[selected_name]
emp = employees_df[employees_df["EMPLOYEE_ID"] == eid].iloc[0]

st.sidebar.markdown("---")
st.sidebar.markdown(f"**{emp['FIRST_NAME']} {emp['LAST_NAME']}**")
st.sidebar.markdown(f"{emp['TITLE']}")
st.sidebar.markdown(f"{emp['DEPARTMENT']} \u00b7 {emp['LOCATION']}")
si = "\U0001F7E2" if emp['STATUS']=='Active' else "\U0001F7E1"
st.sidebar.markdown(f"Status: {si} {emp['STATUS']}")

st.title(f"{emp['FIRST_NAME']} {emp['LAST_NAME']}")
st.caption(f"{emp['TITLE']} \u00b7 {emp['DEPARTMENT']} \u00b7 {emp['LOCATION']}")

tabs = st.tabs(["Overview","Utilization & Time","Bench & Staffing","Projects","Compensation","Recruitment","Leave","People & HR","Skills & Certs","PIP Tracker","Directory","👥 People Dashboard","📊 Performance Dashboard","💬 Ask Your Data"])
tab1,tab2,tab3,tab4,tab5,tab7,tab8,tab9,tab10,tab11,tab12,tab13,tab14,tab_analyst = tabs


# ===== TAB 1: OVERVIEW + RAG =====
with tab1:
    tenure_days = (date.today() - pd.to_datetime(emp['HIRE_DATE']).date()).days
    tenure_years = round(tenure_days / 365.25, 1)
    sal_df = q(f"SELECT * FROM {DB}.{SCH}.SALARY WHERE EMPLOYEE_ID={eid} ORDER BY EFFECTIVE_DATE DESC")
    cs = sal_df.iloc[0] if len(sal_df) > 0 else None
    util_df = q(f"SELECT * FROM {DB}.{SCH}.UTILIZATION WHERE EMPLOYEE_ID={eid}")
    avg_u = round(util_df["UTILIZATION_RATE"].mean(), 1) if len(util_df) > 0 else 0
    proj_df = q(f"SELECT pa.*, p.STATUS AS PS FROM {DB}.{SCH}.PROJECT_ASSIGNMENTS pa JOIN {DB}.{SCH}.PROJECTS p ON pa.PROJECT_ID=p.PROJECT_ID WHERE pa.EMPLOYEE_ID={eid}")
    ap = len(proj_df[proj_df["PS"]=="Active"]) if len(proj_df) > 0 else 0

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Tenure",f"{tenure_years} yrs")
    c2.metric("Avg Utilization",f"{avg_u}%")
    c3.metric("Active Projects",ap)
    c4.metric("Annual Leave",f"{emp['ANNUAL_LEAVE_BALANCE']:.1f} days" if pd.notna(emp['ANNUAL_LEAVE_BALANCE']) else "N/A")
    c5.metric("Base Salary",f"${emp['BASE_SALARY']:,.0f}" if pd.notna(emp['BASE_SALARY']) else "N/A")

    col1,col2 = st.columns(2)
    with col1:
        st.subheader("Employee Details")
        st.markdown(f"**Email:** {emp['EMAIL']}")
        st.markdown(f"**Hire Date:** {emp['HIRE_DATE']}")
        st.markdown(f"**Location:** {emp['LOCATION']}")
        st.markdown(f"**Employee ID:** {emp['EMPLOYEE_ID']}")
        if emp['MANAGER_ID'] and pd.notna(emp['MANAGER_ID']):
            mgr = employees_df[employees_df['EMPLOYEE_ID']==int(emp['MANAGER_ID'])]
            if len(mgr)>0:
                mgr=mgr.iloc[0]
                st.markdown(f"**Manager:** {mgr['FIRST_NAME']} {mgr['LAST_NAME']}")
    with col2:
        st.subheader("Quick Summary")
        if cs is not None:
            st.markdown(f"**Base Salary:** ${cs['BASE_SALARY']:,.0f}")
            st.markdown(f"**Total Comp:** ${cs['BASE_SALARY']+cs['BONUS']:,.0f}")
        comp_df = q(f"SELECT * FROM {DB}.{SCH}.EMPLOYEE_COMPENSATION_DETAILS WHERE EMPLOYEE_ID={eid}")
        if len(comp_df)>0:
            cd=comp_df.iloc[0]
            st.markdown(f"**PIP Status:** {cd['PIP_STATUS']}")
            st.markdown(f"**Next Review:** {cd['NEXT_REVIEW_DATE']}")

    st.subheader("Department Headcount")
    dept_df = q(f"SELECT DEPARTMENT, ACTIVE AS HEADCOUNT FROM {DB}.{SCH}.HEADCOUNT_BY_DEPARTMENT ORDER BY ACTIVE DESC")
    st.bar_chart(dept_df.set_index("DEPARTMENT"))

    st.markdown("---")
    st.subheader("\U0001F50D Company Knowledge Assistant")

    current_user = session.sql("SELECT CURRENT_USER()").to_pandas().iloc[0, 0]

    sessions_df = session.sql(f"SELECT SESSION_ID, SESSION_NAME, CREATED_AT FROM {DB}.{APP_SCH}.CHAT_SESSIONS WHERE USERNAME='{current_user}' ORDER BY LAST_ACTIVE DESC").to_pandas()

    col_new, col_sel = st.columns([1, 3])
    with col_new:
        if st.button("\u2795 New Chat", key="new_chat"):
            session.sql(f"INSERT INTO {DB}.{APP_SCH}.CHAT_SESSIONS (USERNAME, SESSION_NAME) SELECT '{current_user}', 'Chat ' || (COALESCE(MAX(SESSION_ID),0)+1)::VARCHAR FROM {DB}.{APP_SCH}.CHAT_SESSIONS").collect()
            st.rerun()

    with col_sel:
        if len(sessions_df) > 0:
            session_options = {f"{r['SESSION_NAME']} ({str(r['CREATED_AT'])[:16]})": r['SESSION_ID'] for _, r in sessions_df.iterrows()}
            selected_session = st.selectbox("Conversations", list(session_options.keys()), key="chat_session_sel", label_visibility="collapsed")
            active_session_id = session_options[selected_session]
        else:
            session.sql(f"INSERT INTO {DB}.{APP_SCH}.CHAT_SESSIONS (USERNAME, SESSION_NAME) SELECT '{current_user}', 'Chat 1'").collect()
            st.rerun()

    messages_df = session.sql(f"SELECT ROLE, CONTENT, SOURCES, CREATED_AT FROM {DB}.{APP_SCH}.CHAT_MESSAGES WHERE SESSION_ID={active_session_id} AND USERNAME='{current_user}' ORDER BY CREATED_AT").to_pandas()

    suggested = st.columns(3)
    with suggested[0]:
        if st.button("Health plans?", key="s1"):
            st.session_state.rag_input = "What health insurance plans does the company offer and what are the costs?"
    with suggested[1]:
        if st.button("Upcoming events?", key="s2"):
            st.session_state.rag_input = "What company events are coming up in the next few months?"
    with suggested[2]:
        if st.button("PTO policy?", key="s3"):
            st.session_state.rag_input = "How much PTO do I get and what is the time off policy?"

    chat_canvas = st.container(height=450)
    with chat_canvas:
        if len(messages_df) > 0:
            for _, msg in messages_df.iterrows():
                with st.chat_message(msg["ROLE"]):
                    st.markdown(msg["CONTENT"])
                    if msg["SOURCES"] and str(msg["SOURCES"]).strip():
                        with st.expander("Sources"):
                            for s in json.loads(msg["SOURCES"]):
                                st.markdown(f"- {s}")
        else:
            st.caption("Start a conversation by asking a question below.")

    default_input = st.session_state.pop("rag_input", None)
    user_q = st.chat_input("Ask about company info, benefits, events...") or default_input

    if user_q:
        safe_content = user_q.replace("'", "''")
        session.sql(f"INSERT INTO {DB}.{APP_SCH}.CHAT_MESSAGES (SESSION_ID, USERNAME, ROLE, CONTENT, SOURCES) VALUES ({active_session_id}, '{current_user}', 'user', '{safe_content}', NULL)").collect()

        safe_q = user_q.replace("\\", "\\\\").replace('"', '\\"')
        search_json = '{"query": "' + safe_q + '", "columns": ["CONTENT", "TITLE", "CATEGORY"], "limit": 3}'
        search_df = session.sql(
            "SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(?, ?) AS RESULTS",
            params=['DEMO_EMPLOYEE_APP.PUBLIC.COMPANY_KB_SEARCH', search_json]
        ).to_pandas()

        context_parts = []
        sources = []
        if len(search_df) > 0:
            res = json.loads(search_df.iloc[0]["RESULTS"])
            for r in res.get("results", []):
                context_parts.append(r.get("CONTENT", ""))
                sources.append(f"**{r.get('CATEGORY', '')}** - {r.get('TITLE', '')}")

        context_text = "\n\n---\n\n".join(context_parts) if context_parts else "No relevant information found."
        prompt_text = f"""You are a helpful company assistant for Acme Solutions Inc. Answer the employee question based ONLY on the context below. Be specific with dates, numbers, and details. If the context does not contain the answer, say so.

Context:
{context_text}

Question: {user_q}

Answer in clear markdown with specific details."""

        answer_df = session.sql("SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-large2', ?) AS ANSWER", params=[prompt_text]).to_pandas()
        answer = answer_df.iloc[0]["ANSWER"] if len(answer_df) > 0 else "Sorry, I could not generate a response."

        safe_answer = answer.replace("'", "''")
        sources_json = json.dumps(sources).replace("'", "''")
        session.sql(f"INSERT INTO {DB}.{APP_SCH}.CHAT_MESSAGES (SESSION_ID, USERNAME, ROLE, CONTENT, SOURCES) VALUES ({active_session_id}, '{current_user}', 'assistant', '{safe_answer}', '{sources_json}')").collect()
        session.sql(f"UPDATE {DB}.{APP_SCH}.CHAT_SESSIONS SET LAST_ACTIVE=CURRENT_TIMESTAMP() WHERE SESSION_ID={active_session_id}").collect()

        if len(messages_df) == 0:
            short_name = user_q[:50].replace("'", "''")
            session.sql(f"UPDATE {DB}.{APP_SCH}.CHAT_SESSIONS SET SESSION_NAME='{short_name}' WHERE SESSION_ID={active_session_id}").collect()

        st.rerun()

# ===== TAB 2: UTILIZATION & TIME =====
with tab2:
    st.subheader("Utilization Trend")
    util_df = q(f"SELECT * FROM {DB}.{SCH}.UTILIZATION WHERE EMPLOYEE_ID={eid} ORDER BY MONTH")
    if len(util_df)>0:
        ch = util_df[["MONTH","UTILIZATION_RATE","TARGET_RATE"]].copy()
        ch["MONTH"]=pd.to_datetime(ch["MONTH"])
        ch=ch.set_index("MONTH")
        st.line_chart(ch,color=["#4CAF50","#FF5722"])
        c1,c2,c3=st.columns(3)
        c1.metric("Average",f"{util_df['UTILIZATION_RATE'].mean():.1f}%")
        c2.metric("Max",f"{util_df['UTILIZATION_RATE'].max():.1f}%")
        c3.metric("Min",f"{util_df['UTILIZATION_RATE'].min():.1f}%")

    st.subheader("Time Entries (Last 12 Weeks)")
    tdf = q(f"SELECT te.SPENT_DATE,te.HOURS,te.IS_BILLABLE,t.TASK_NAME,p.PROJECT_NAME FROM {DB}.{SCH}.TIME_ENTRIES te JOIN {DB}.{SCH}.TASKS t ON te.TASK_ID=t.TASK_ID JOIN {DB}.{SCH}.PROJECTS p ON te.PROJECT_ID=p.PROJECT_ID WHERE te.EMPLOYEE_ID={eid} ORDER BY te.SPENT_DATE DESC")
    if len(tdf)>0:
        c1,c2,c3=st.columns(3)
        th=tdf["HOURS"].sum()
        bh=tdf[tdf["IS_BILLABLE"]==True]["HOURS"].sum()
        c1.metric("Total Hours",f"{th:.1f}")
        c2.metric("Billable Hours",f"{bh:.1f}")
        c3.metric("Billable %",f"{(bh/th*100):.0f}%" if th>0 else "0%")
        wk=tdf.copy()
        wk["SPENT_DATE"]=pd.to_datetime(wk["SPENT_DATE"])
        wk["WEEK"]=wk["SPENT_DATE"].dt.isocalendar().week.astype(str)
        wa=wk.groupby(["WEEK","IS_BILLABLE"])["HOURS"].sum().reset_index()
        wa["TYPE"]=wa["IS_BILLABLE"].map({True:"Billable",False:"Non-Billable"})
        pv=wa.pivot_table(index="WEEK",columns="TYPE",values="HOURS",fill_value=0)
        st.bar_chart(pv)
        st.subheader("Hours by Project")
        bp=tdf.groupby("PROJECT_NAME")["HOURS"].sum().sort_values(ascending=False)
        st.bar_chart(bp)

# ===== TAB 3: BENCH & STAFFING =====
with tab3:
    st.subheader("Bench Analysis")
    bsql=f"""SELECT e.EMPLOYEE_ID,e.FIRST_NAME,e.LAST_NAME,e.DEPARTMENT,e.TITLE,e.LOCATION,
        COALESCE(SUM(CASE WHEN p.STATUS='Active' THEN pa.ALLOCATION_PCT END),0) AS ACTIVE_ALLOC,
        COUNT(CASE WHEN p.STATUS='Active' THEN 1 END) AS ACTIVE_PROJ
        FROM {DB}.{SCH}.EMPLOYEES e
        LEFT JOIN {DB}.{SCH}.PROJECT_ASSIGNMENTS pa ON e.EMPLOYEE_ID=pa.EMPLOYEE_ID
        LEFT JOIN {DB}.{SCH}.PROJECTS p ON pa.PROJECT_ID=p.PROJECT_ID
        WHERE e.STATUS='Active' GROUP BY 1,2,3,4,5,6 ORDER BY ACTIVE_ALLOC"""
    bdf=q(bsql)
    ob=bdf[bdf["ACTIVE_ALLOC"]<30]
    pa2=bdf[(bdf["ACTIVE_ALLOC"]>=30)&(bdf["ACTIVE_ALLOC"]<80)]
    fu=bdf[bdf["ACTIVE_ALLOC"]>=80]
    c1,c2,c3,c4=st.columns(4)
    c1.metric("On Bench (<30%)",len(ob))
    c2.metric("Partial (30-79%)",len(pa2))
    c3.metric("Fully Allocated (80%+)",len(fu))
    c4.metric("Total Active",len(bdf))
    st.subheader("Bench by Department")
    bd=ob.groupby("DEPARTMENT").size().reset_index(name="COUNT")
    if len(bd)>0: st.bar_chart(bd.set_index("DEPARTMENT"))
    st.subheader("Employees on Bench")
    if len(ob)>0:
        st.dataframe(ob[["FIRST_NAME","LAST_NAME","DEPARTMENT","TITLE","LOCATION","ACTIVE_ALLOC","ACTIVE_PROJ"]].rename(columns={"ACTIVE_ALLOC":"Allocation %","ACTIVE_PROJ":"Active Projects"}),use_container_width=True,hide_index=True)
    else: st.success("No employees on bench!")
    st.subheader("Who's on Which Project?")
    sdf=q(f"SELECT p.PROJECT_NAME,p.STATUS AS PS,e.FIRST_NAME||' '||e.LAST_NAME AS EMP,e.DEPARTMENT,pa.ROLE,pa.ALLOCATION_PCT FROM {DB}.{SCH}.PROJECT_ASSIGNMENTS pa JOIN {DB}.{SCH}.PROJECTS p ON pa.PROJECT_ID=p.PROJECT_ID JOIN {DB}.{SCH}.EMPLOYEES e ON pa.EMPLOYEE_ID=e.EMPLOYEE_ID WHERE p.STATUS='Active' ORDER BY p.PROJECT_NAME,pa.ALLOCATION_PCT DESC")
    
    st.markdown("---")
    st.subheader("Harvest User Assignments (Rates & PM Flags)")
    ua=q(f"""SELECT hu.FIRST_NAME||' '||hu.LAST_NAME AS NAME, hu.ROLES, p.PROJECT_NAME, ua.IS_PROJECT_MANAGER,
        ua.HOURLY_RATE, ua.BUDGET, hu.DEFAULT_HOURLY_RATE, hu.COST_RATE, hu.WEEKLY_CAPACITY
        FROM {DB}.{SCH}.USER_ASSIGNMENTS ua
        JOIN {DB}.{SCH}.HARVEST_USERS hu ON ua.USER_ID=hu.USER_ID
        JOIN {DB}.{SCH}.PROJECTS p ON ua.PROJECT_ID=p.PROJECT_ID
        WHERE ua.IS_ACTIVE=TRUE AND p.STATUS='Active'
        ORDER BY ua.IS_PROJECT_MANAGER DESC, NAME""")
    if len(ua)>0:
        pms=ua[ua["IS_PROJECT_MANAGER"]==True]
        st.markdown(f"**{len(pms)} Project Manager assignments** across active projects")
        st.dataframe(ua, use_container_width=True, hide_index=True)

    if len(sdf)>0:
        sp=st.selectbox("Filter by Project",["All"]+sdf["PROJECT_NAME"].unique().tolist())
        ds=sdf if sp=="All" else sdf[sdf["PROJECT_NAME"]==sp]
        st.dataframe(ds,use_container_width=True,hide_index=True)

# ===== TAB 4: PROJECTS =====
with tab4:
    st.subheader("Project Assignments")
    pd2=q(f"""SELECT pa.ASSIGNMENT_ID, pa.EMPLOYEE_ID, pa.PROJECT_ID, pa.ROLE, pa.ALLOCATION_PCT,
        pa.START_DATE, pa.END_DATE, pa.HOURLY_RATE AS PA_HOURLY_RATE, pa.BUDGET AS PA_BUDGET, pa.IS_PROJECT_MANAGER,
        p.PROJECT_NAME, p.CLIENT, p.STATUS AS PS, p.START_DATE AS P_S, p.END_DATE AS P_E, p.BUDGET AS PROJECT_BUDGET,
        pb.HOURS_SPENT, pb.HOURS_REMAINING, pb.AMOUNT_SPENT, pb.AMOUNT_REMAINING
        FROM {DB}.{SCH}.PROJECT_ASSIGNMENTS pa JOIN {DB}.{SCH}.PROJECTS p ON pa.PROJECT_ID=p.PROJECT_ID
        LEFT JOIN {DB}.{SCH}.PROJECT_BUDGETS pb ON p.PROJECT_ID=pb.PROJECT_ID
        WHERE pa.EMPLOYEE_ID={eid} ORDER BY p.STATUS,pa.ALLOCATION_PCT DESC""")
    if len(pd2)>0:
        ta=pd2["ALLOCATION_PCT"].sum()
        ac=pd2[pd2["PS"]=="Active"]
        c1,c2,c3=st.columns(3)
        c1.metric("Total Allocation",f"{ta:.0f}%")
        c2.metric("Active Projects",len(ac))
        c3.metric("Total Projects",len(pd2))
        if ta>100: st.warning(f"Over-allocated at {ta:.0f}%!")
        elif ta<70: st.info(f"Has capacity at {ta:.0f}% allocation.")
        for _,p in ac.iterrows():
            with st.expander(f"{p['PROJECT_NAME']} - {p['CLIENT']} ({p['ALLOCATION_PCT']:.0f}%)"):
                c1,c2,c3=st.columns(3)
                c1.markdown(f"**Role:** {p['ROLE']}")
                c2.markdown(f"**Duration:** {p['P_S']} to {p['P_E']}")
                c3.markdown(f"**Budget:** ${p['PROJECT_BUDGET']:,.0f}" if pd.notna(p['PROJECT_BUDGET']) else "")
                if pd.notna(p.get('HOURS_SPENT')) and pd.notna(p.get('HOURS_REMAINING')):
                    tt=p['HOURS_SPENT']+p['HOURS_REMAINING']
                    pc2=(p['HOURS_SPENT']/tt*100) if tt>0 else 0
                    st.progress(min(pc2/100,1.0),text=f"Budget: {pc2:.0f}% ({p['HOURS_SPENT']:.0f}/{tt:.0f} hrs)")
    else: st.info("No project assignments.")

    st.markdown("---")
    st.subheader("Harvest Rates & Budget Breakdown")
    rates_df=q(f"""SELECT p.PROJECT_NAME, p.HOURLY_RATE, p.FEES, p.COST_BUDGET, p.BUDGET_BY, p.IS_BILLABLE,
        ROUND(p.FEES - p.COST_BUDGET, 0) AS GROSS_MARGIN,
        ROUND((p.FEES - p.COST_BUDGET) / NULLIF(p.FEES,0) * 100, 1) AS MARGIN_PCT
        FROM {DB}.{SCH}.PROJECTS p WHERE p.STATUS='Active' ORDER BY GROSS_MARGIN DESC""")
    if len(rates_df)>0:
        c1,c2,c3=st.columns(3)
        c1.metric("Total Fees", f"${rates_df['FEES'].sum():,.0f}")
        c2.metric("Total Cost Budget", f"${rates_df['COST_BUDGET'].sum():,.0f}")
        c3.metric("Projected Margin", f"${rates_df['GROSS_MARGIN'].sum():,.0f}")
        st.dataframe(rates_df, use_container_width=True, hide_index=True)

    st.subheader("Budget Allocation by Team Member (Selected Employee Projects)")
    alloc_df=q(f"""SELECT p.PROJECT_NAME, pa.ROLE, pa.ALLOCATION_PCT, pa.HOURLY_RATE, pa.BUDGET, pa.IS_PROJECT_MANAGER
        FROM {DB}.{SCH}.PROJECT_ASSIGNMENTS pa JOIN {DB}.{SCH}.PROJECTS p ON pa.PROJECT_ID=p.PROJECT_ID
        WHERE pa.EMPLOYEE_ID={eid} AND p.STATUS='Active' ORDER BY pa.BUDGET DESC""")
    if len(alloc_df)>0:
        st.dataframe(alloc_df, use_container_width=True, hide_index=True)

    st.subheader("All Active Project Budgets")
    budg=q(f"SELECT p.PROJECT_NAME,p.CLIENT,pb.BUDGET_AMOUNT,pb.AMOUNT_SPENT,pb.AMOUNT_REMAINING,ROUND(pb.AMOUNT_SPENT/pb.BUDGET_AMOUNT*100,1) AS BURN_PCT FROM {DB}.{SCH}.PROJECT_BUDGETS pb JOIN {DB}.{SCH}.PROJECTS p ON pb.PROJECT_ID=p.PROJECT_ID WHERE p.STATUS='Active' ORDER BY BURN_PCT DESC")
    if len(budg)>0: st.dataframe(budg,use_container_width=True,hide_index=True)

# ===== TAB 5: COMPENSATION =====
with tab5:
    st.subheader("Compensation")
    sdf2=q(f"SELECT * FROM {DB}.{SCH}.SALARY WHERE EMPLOYEE_ID={eid} ORDER BY EFFECTIVE_DATE DESC")
    cdf=q(f"SELECT * FROM {DB}.{SCH}.EMPLOYEE_COMPENSATION_DETAILS WHERE EMPLOYEE_ID={eid}")
    if len(sdf2)>0:
        cu=sdf2.iloc[0]
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Base Salary",f"${cu['BASE_SALARY']:,.0f}")
        c2.metric("Bonus",f"${cu['BONUS']:,.0f}")
        c3.metric("Total Cash",f"${cu['BASE_SALARY']+cu['BONUS']:,.0f}")
        if len(cdf)>0: c4.metric("Equity Value",f"${cdf.iloc[0]['EQUITY_VALUE_ESTIMATE']:,.0f}")
        if len(sdf2)>1:
            pv2=sdf2.iloc[1]
            chg=cu['BASE_SALARY']-pv2['BASE_SALARY']
            pcc=(chg/pv2['BASE_SALARY'])*100
            st.markdown(f"**Last raise:** ${chg:+,.0f} ({pcc:+.1f}%)")
    if len(cdf)>0:
        cd=cdf.iloc[0]
        st.subheader("Equity & Benefits")
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Stock Options",f"{cd['STOCK_OPTIONS']:,}")
        c2.metric("Shares Vested",f"{cd['SHARES_VESTED']:,}")
        c3.metric("401k Match",f"{cd['EMPLOYER_MATCH_PCT']}%")
        c4.metric("Pay Frequency",cd['PAY_FREQUENCY'])
        c1,c2,c3,c4=st.columns(4)
        c1.metric("OT Eligible","Yes" if cd['OVERTIME_ELIGIBLE'] else "No")
        c2.metric("Signing Bonus",f"${cd['SIGNING_BONUS']:,.0f}")
        c3.metric("Training Budget",f"${cd['TRAINING_BUDGET']:,.0f}")
        c4.metric("Training Used",f"${cd['TRAINING_BUDGET_USED']:,.0f}")
        st.subheader("Leave Balances")
        c1,c2,c3=st.columns(3)
        c1.metric("Annual Leave",f"{cd['ANNUAL_LEAVE_BALANCE']:.1f} days")
        c2.metric("Sick Leave",f"{cd['SICK_LEAVE_BALANCE']:.1f} days")
        c3.metric("Personal Leave",f"{cd['PERSONAL_LEAVE_BALANCE']:.1f} days")
        if cd['LAST_PROMOTION_DATE'] and pd.notna(cd['LAST_PROMOTION_DATE']):
            st.markdown(f"**Last Promotion:** {cd['LAST_PROMOTION_DATE']} (from {cd['LAST_PROMOTION_FROM']})")
        st.markdown(f"**Next Review Date:** {cd['NEXT_REVIEW_DATE']}")
        if cd['PIP_STATUS'] not in ['None',None]:
            st.error(f"PIP Status: {cd['PIP_STATUS']} ({cd['PIP_START_DATE']} to {cd['PIP_END_DATE']})")
    if len(sdf2)>0:
        st.subheader("Salary History")
        hs=sdf2[["EFFECTIVE_DATE","BASE_SALARY","BONUS"]].copy()
        hs["TOTAL"]=hs["BASE_SALARY"]+hs["BONUS"]
        hs["EFFECTIVE_DATE"]=pd.to_datetime(hs["EFFECTIVE_DATE"]).dt.strftime("%b %Y")
        st.dataframe(hs,use_container_width=True,hide_index=True)
    st.subheader("Expenses")
    edf=q(f"SELECT e.EXPENSE_DATE,e.CATEGORY,e.AMOUNT,e.IS_BILLABLE,p.PROJECT_NAME,e.NOTES FROM {DB}.{SCH}.EXPENSE_ENTRIES e JOIN {DB}.{SCH}.PROJECTS p ON e.PROJECT_ID=p.PROJECT_ID WHERE e.EMPLOYEE_ID={eid} ORDER BY e.EXPENSE_DATE DESC")
    if len(edf)>0:
        c1,c2=st.columns(2)
        c1.metric("Total Expenses",f"${edf['AMOUNT'].sum():,.2f}")
        c2.metric("Billable",f"${edf[edf['IS_BILLABLE']==True]['AMOUNT'].sum():,.2f}")
        st.dataframe(edf,use_container_width=True,hide_index=True)
    else: st.info("No expenses.")

# ===== TAB 7: RECRUITMENT =====
with tab7:
    st.subheader("Recruitment Pipeline")
    cdf3=q(f"SELECT c.*,j.TITLE AS JOB_TITLE,j.DEPARTMENT FROM {DB}.{SCH}.CANDIDATES c JOIN {DB}.{SCH}.JOB_POSTINGS j ON c.JOB_ID=j.JOB_ID")
    jdf=q(f"SELECT * FROM {DB}.{SCH}.JOB_POSTINGS ORDER BY CREATED_DATE DESC")
    if len(cdf3)>0:
        ac3=cdf3[cdf3["STATUS"]=="Active"]
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Total Candidates",len(cdf3))
        c2.metric("Active Pipeline",len(ac3))
        c3.metric("Open Positions",len(jdf[jdf["STATUS"]=="Open"]))
        c4.metric("Total Openings",int(jdf[jdf["STATUS"]=="Open"]["OPENINGS"].sum()))
        st.subheader("Pipeline by Stage")
        so=["Application Review","Phone Screen","Technical Interview","Final Round","Offer","Hired"]
        sc=ac3["STAGE"].value_counts().reindex(so,fill_value=0)
        st.bar_chart(sc)
        st.subheader("By Source")
        st.bar_chart(cdf3["SOURCE"].value_counts())
        st.subheader("Open Positions")
        oj=jdf[jdf["STATUS"]=="Open"][["TITLE","DEPARTMENT","JOB_TYPE","LOCATION","OPENINGS","APPLICANTS_COUNT","SALARY_MIN","SALARY_MAX"]]
        st.dataframe(oj,use_container_width=True,hide_index=True)
        st.subheader("Active Candidates")
        df2=st.selectbox("Filter Dept",["All"]+sorted(ac3["DEPARTMENT"].unique().tolist()),key="r_d")
        sc2=ac3 if df2=="All" else ac3[ac3["DEPARTMENT"]==df2]
        st.dataframe(sc2[["FIRST_NAME","LAST_NAME","JOB_TITLE","STAGE","SOURCE","APPLIED_DATE","RATING"]].sort_values("APPLIED_DATE",ascending=False),use_container_width=True,hide_index=True)

# ===== TAB 8: LEAVE =====
with tab8:
    st.subheader("Leave & Attendance")
    ldf=q(f"SELECT lr.*,e.FIRST_NAME,e.LAST_NAME FROM {DB}.{SCH}.LEAVE_REQUESTS lr JOIN {DB}.{SCH}.EMPLOYEES e ON lr.EMPLOYEE_ID=e.EMPLOYEE_ID ORDER BY lr.START_DATE DESC")
    el=ldf[ldf["EMPLOYEE_ID"]==eid]
    cdf4=q(f"SELECT * FROM {DB}.{SCH}.EMPLOYEE_COMPENSATION_DETAILS WHERE EMPLOYEE_ID={eid}")
    if len(cdf4)>0:
        cd2=cdf4.iloc[0]
        c1,c2,c3=st.columns(3)
        c1.metric("Annual Leave Bal",f"{cd2['ANNUAL_LEAVE_BALANCE']:.1f} days")
        c2.metric("Sick Leave Bal",f"{cd2['SICK_LEAVE_BALANCE']:.1f} days")
        c3.metric("Personal Leave Bal",f"{cd2['PERSONAL_LEAVE_BALANCE']:.1f} days")
    if len(el)>0:
        st.subheader(f"Leave History - {emp['FIRST_NAME']}")
        apd=el[el["STATUS"]=="Approved"]["DAYS"].sum()
        pnd=el[el["STATUS"]=="Pending"]["DAYS"].sum()
        c1,c2,c3=st.columns(3)
        c1.metric("Approved Days",f"{apd:.0f}")
        c2.metric("Pending Days",f"{pnd:.0f}")
        c3.metric("Total Requests",len(el))
        st.dataframe(el[["LEAVE_TYPE","START_DATE","END_DATE","DAYS","STATUS","REASON"]],use_container_width=True,hide_index=True)
    st.subheader("Team Leave Calendar (Upcoming)")
    up=ldf[(ldf["STATUS"].isin(["Approved","Pending"]))&(pd.to_datetime(ldf["END_DATE"])>=pd.Timestamp(date.today()))]
    if len(up)>0:
        up2=up.copy()
        up2["EMPLOYEE"]=up2["FIRST_NAME"]+" "+up2["LAST_NAME"]
        st.dataframe(up2[["EMPLOYEE","LEAVE_TYPE","START_DATE","END_DATE","DAYS","STATUS"]].sort_values("START_DATE"),use_container_width=True,hide_index=True)
    st.subheader("Leave by Type (All)")
    lt=q(f"SELECT LEAVE_TYPE, TOTAL_DAYS FROM {DB}.{SCH}.LEAVE_SUMMARY WHERE STATUS='Approved' ORDER BY TOTAL_DAYS DESC")
    if len(lt)>0:
        st.bar_chart(lt.set_index("LEAVE_TYPE"))

# ===== TAB 9: PEOPLE & HR =====
with tab9:
    st.subheader("People & HR - PII Profile")
    pii=q(f"SELECT * FROM {DB}.{SCH}.EMPLOYEE_PII WHERE EMPLOYEE_ID={eid}")
    ef=q(f"SELECT * FROM {DB}.{SCH}.EMPLOYEE_FIELDS WHERE EMPLOYEE_ID={eid}")
    if len(pii)>0:
        p=pii.iloc[0]
        col1,col2,col3=st.columns(3)
        with col1:
            st.markdown("**Personal Information**")
            st.markdown(f"SSN: {p['SSN']}")
            st.markdown(f"Passport: {p['PASSPORT_NUMBER']}")
            st.markdown(f"Passport Expiry: {p['PASSPORT_EXPIRY']}")
            st.markdown(f"Marital Status: {p['MARITAL_STATUS']}")
            st.markdown(f"Dependents: {p['DEPENDENTS_COUNT']}")
            st.markdown(f"Pronouns: {p['PREFERRED_PRONOUNS']}")
        with col2:
            st.markdown("**Work Authorization**")
            st.markdown(f"Visa Status: {p['VISA_STATUS']}")
            if p['VISA_EXPIRY'] and pd.notna(p['VISA_EXPIRY']):
                days_left = (pd.to_datetime(p['VISA_EXPIRY']).date() - date.today()).days
                st.markdown(f"Visa Expiry: {p['VISA_EXPIRY']}")
                if days_left < 180: st.error(f"VISA EXPIRING IN {days_left} DAYS!")
                elif days_left < 365: st.warning(f"Visa renewal needed within {days_left} days")
            st.markdown(f"License: {p['DRIVERS_LICENSE']} ({p['DRIVERS_LICENSE_STATE']})")
            st.markdown(f"License Expiry: {p['DRIVERS_LICENSE_EXPIRY']}")
        with col3:
            st.markdown("**Address**")
            st.markdown(f"{p['HOME_ADDRESS']}")
            st.markdown(f"{p['CITY']}, {p['STATE']} {p['ZIP_CODE']}")
            st.markdown(f"{p['COUNTRY']}")
            st.markdown(f"LinkedIn: {p['LINKEDIN_URL']}")
        st.subheader("Benefits & Insurance")
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Health Plan",p['HEALTH_INSURANCE_PLAN'])
        c2.metric("Dental",p['DENTAL_PLAN'])
        c3.metric("Vision",p['VISION_PLAN'])
        c4.metric("Life Insurance",f"${p['LIFE_INSURANCE_COVERAGE']:,.0f}")
        st.markdown(f"**Health ID:** {p['HEALTH_INSURANCE_ID']}")
        st.markdown(f"**Bank:** {p['BANK_NAME']} (****{p['BANK_ACCOUNT_LAST4']})")
        st.subheader("EEO & Compliance")
        c1,c2,c3,c4=st.columns(4)
        c1.markdown(f"**Ethnicity:** {p['ETHNICITY']}")
        c2.markdown(f"**Veteran:** {p['VETERAN_STATUS']}")
        c3.markdown(f"**Disability:** {p['DISABILITY_STATUS']}")
        if len(ef)>0: c4.markdown(f"**Nationality:** {ef.iloc[0]['NATIONALITY']}")
        st.subheader("Event Planning Info")
        c1,c2=st.columns(2)
        c1.markdown(f"**T-Shirt Size:** {p['T_SHIRT_SIZE']}")
        c2.markdown(f"**Dietary:** {p['DIETARY_RESTRICTIONS']}")
    st.subheader("Visa Expiry Alerts (All Employees)")
    va=q(f"SELECT e.FIRST_NAME||' '||e.LAST_NAME AS NAME,e.DEPARTMENT,p.VISA_STATUS,p.VISA_EXPIRY,DATEDIFF('day',CURRENT_DATE(),p.VISA_EXPIRY) AS DAYS_LEFT FROM {DB}.{SCH}.EMPLOYEE_PII p JOIN {DB}.{SCH}.EMPLOYEES e ON p.EMPLOYEE_ID=e.EMPLOYEE_ID WHERE p.VISA_STATUS NOT IN ('Citizen') AND p.VISA_EXPIRY IS NOT NULL ORDER BY p.VISA_EXPIRY")
    if len(va)>0: st.dataframe(va,use_container_width=True,hide_index=True)
    st.subheader("Demographics Overview")
    c1,c2=st.columns(2)
    with c1:
        st.markdown("**By Ethnicity**")
        eth=q(f"SELECT ETHNICITY,COUNT(*) AS CNT FROM {DB}.{SCH}.EMPLOYEE_PII GROUP BY ETHNICITY ORDER BY CNT DESC")
        st.bar_chart(eth.set_index("ETHNICITY"))
    with c2:
        st.markdown("**By Insurance Plan**")
        ins=q(f"SELECT HEALTH_INSURANCE_PLAN,COUNT(*) AS CNT FROM {DB}.{SCH}.EMPLOYEE_PII GROUP BY HEALTH_INSURANCE_PLAN ORDER BY CNT DESC")
        st.bar_chart(ins.set_index("HEALTH_INSURANCE_PLAN"))

# ===== TAB 10: SKILLS & CERTS =====
with tab10:
    st.subheader("Skills & Certifications")
    cr=q(f"SELECT * FROM {DB}.{SCH}.EMPLOYEE_CERTIFICATIONS WHERE EMPLOYEE_ID={eid} ORDER BY EXPIRY_DATE")
    if len(cr)>0:
        ac4=cr[cr["STATUS"]=="Active"]
        ex4=cr[cr["STATUS"]=="Expired"]
        c1,c2,c3=st.columns(3)
        c1.metric("Active Certs",len(ac4))
        c2.metric("Expired Certs",len(ex4))
        c3.metric("Total",len(cr))
        st.dataframe(cr[["CERTIFICATION_NAME","ISSUING_BODY","ISSUE_DATE","EXPIRY_DATE","STATUS","SKILL_CATEGORY"]],use_container_width=True,hide_index=True)
    else: st.info("No certifications on file.")
    st.subheader("Expiring Certifications (Next 6 Months)")
    exp2=q(f"SELECT e.FIRST_NAME||' '||e.LAST_NAME AS NAME,e.DEPARTMENT,c.CERTIFICATION_NAME,c.ISSUING_BODY,c.EXPIRY_DATE,DATEDIFF('day',CURRENT_DATE(),c.EXPIRY_DATE) AS DAYS_LEFT FROM {DB}.{SCH}.EMPLOYEE_CERTIFICATIONS c JOIN {DB}.{SCH}.EMPLOYEES e ON c.EMPLOYEE_ID=e.EMPLOYEE_ID WHERE c.STATUS='Active' AND c.EXPIRY_DATE IS NOT NULL AND c.EXPIRY_DATE<=DATEADD('month',6,CURRENT_DATE()) ORDER BY c.EXPIRY_DATE")
    if len(exp2)>0:
        st.warning(f"{len(exp2)} certifications expiring!")
        st.dataframe(exp2,use_container_width=True,hide_index=True)
    else: st.success("No certs expiring in 6 months.")
    st.subheader("Skills Search")
    all_c=q(f"SELECT DISTINCT CERTIFICATION_NAME FROM {DB}.{SCH}.EMPLOYEE_CERTIFICATIONS WHERE STATUS='Active' ORDER BY CERTIFICATION_NAME")
    if len(all_c)>0:
        sel_c=st.selectbox("Select Certification",all_c["CERTIFICATION_NAME"].tolist())
        matched=q(f"SELECT e.FIRST_NAME||' '||e.LAST_NAME AS NAME,e.DEPARTMENT,e.TITLE,c.EXPIRY_DATE,c.SKILL_CATEGORY FROM {DB}.{SCH}.EMPLOYEE_CERTIFICATIONS c JOIN {DB}.{SCH}.EMPLOYEES e ON c.EMPLOYEE_ID=e.EMPLOYEE_ID WHERE c.CERTIFICATION_NAME='{sel_c}' AND c.STATUS='Active'")
        st.dataframe(matched,use_container_width=True,hide_index=True)
    st.subheader("By Category")
    cat=q(f"SELECT SKILL_CATEGORY,COUNT(*) AS CNT FROM {DB}.{SCH}.EMPLOYEE_CERTIFICATIONS WHERE STATUS='Active' GROUP BY SKILL_CATEGORY ORDER BY CNT DESC")
    if len(cat)>0: st.bar_chart(cat.set_index("SKILL_CATEGORY"))

# ===== TAB 11: PIP TRACKER =====
with tab11:
    st.subheader("PIP / Performance Review Tracker")
    st.caption("Employees on a Performance Improvement Plan or flagged for review (OmniHR compensation/review data).")
    pip=q(f"SELECT e.FIRST_NAME||' '||e.LAST_NAME AS NAME,e.DEPARTMENT,e.TITLE,cd.PIP_STATUS,cd.PIP_START_DATE,cd.PIP_END_DATE FROM {DB}.{SCH}.EMPLOYEE_COMPENSATION_DETAILS cd JOIN {DB}.{SCH}.EMPLOYEES e ON cd.EMPLOYEE_ID=e.EMPLOYEE_ID WHERE cd.PIP_STATUS NOT IN ('None') ORDER BY cd.PIP_END_DATE")
    if len(pip)>0:
        st.warning(f"{len(pip)} on PIP/review")
        st.dataframe(pip,use_container_width=True,hide_index=True)
    else: st.success("No PIPs.")

# ===== TAB 12: DIRECTORY =====
with tab12:
    st.subheader("Employee Directory")
    ddf=q(f"SELECT e.EMPLOYEE_ID,e.FIRST_NAME,e.LAST_NAME,e.EMAIL,e.DEPARTMENT,e.TITLE,e.LOCATION,e.STATUS,e.HIRE_DATE,ef.EMPLOYMENT_TYPE,ef.TEAM,ef.PHONE,ef.NATIONALITY,ef.GENDER,p.VISA_STATUS,p.HEALTH_INSURANCE_PLAN,p.PREFERRED_PRONOUNS FROM {DB}.{SCH}.EMPLOYEES e LEFT JOIN {DB}.{SCH}.EMPLOYEE_FIELDS ef ON e.EMPLOYEE_ID=ef.EMPLOYEE_ID LEFT JOIN {DB}.{SCH}.EMPLOYEE_PII p ON e.EMPLOYEE_ID=p.EMPLOYEE_ID ORDER BY e.LAST_NAME")
    sr=st.text_input("Search",placeholder="Name, department, title, team...",key="ds")
    if sr:
        mask=ddf.apply(lambda r: sr.lower() in ' '.join(r.astype(str).values).lower(),axis=1)
        ddf=ddf[mask]
    c1,c2,c3=st.columns(3)
    d_f=c1.selectbox("Department",["All"]+sorted(ddf["DEPARTMENT"].unique().tolist()),key="dd")
    l_f=c2.selectbox("Location",["All"]+sorted(ddf["LOCATION"].unique().tolist()),key="dl")
    t_f=c3.selectbox("Team",["All"]+sorted(ddf["TEAM"].dropna().unique().tolist()),key="dt")
    if d_f!="All": ddf=ddf[ddf["DEPARTMENT"]==d_f]
    if l_f!="All": ddf=ddf[ddf["LOCATION"]==l_f]
    if t_f!="All": ddf=ddf[ddf["TEAM"]==t_f]
    st.markdown(f"**Showing {len(ddf)} employees**")
    st.dataframe(ddf,use_container_width=True,hide_index=True,height=500)

    st.markdown("---")
    st.subheader("Employment History")
    hist_df=q(f"""SELECT CHANGE_TYPE, FROM_VALUE, TO_VALUE, EFFECTIVE_DATE, REASON
        FROM {DB}.{SCH}.EMPLOYEES_HISTORY WHERE EMPLOYEE_ID={eid} ORDER BY EFFECTIVE_DATE""")
    if len(hist_df)>0:
        for _,h in hist_df.iterrows():
            icon={"Hire":"🆕","Promotion":"🏆","Comp Change":"💰","Title Change":"📝","Transfer":"🔄"}.get(h["CHANGE_TYPE"],"📌")
            st.markdown(f"{icon} **{h['EFFECTIVE_DATE']}** — **{h['CHANGE_TYPE']}**: {h['FROM_VALUE'] or 'New'} → {h['TO_VALUE']}  \n  _{h['REASON']}_")
    else:
        st.info("No employment history on file.")

    st.markdown("---")
    st.subheader("Organization Hierarchy")
    org_df=q(f"""SELECT BUSINESS_UNIT, DEPARTMENT, SUB_DEPARTMENT, TEAM,
        COUNT(EMPLOYEE_ID) AS HEADCOUNT
        FROM {DB}.{SCH}.EMPLOYEE_360
        WHERE STATUS='Active'
        GROUP BY BUSINESS_UNIT, DEPARTMENT, SUB_DEPARTMENT, TEAM
        ORDER BY BUSINESS_UNIT, DEPARTMENT, SUB_DEPARTMENT, TEAM""")
    if len(org_df)>0:
        bus=org_df["BUSINESS_UNIT"].dropna().unique().tolist()
        for bu in bus:
            with st.expander(f"🏢 {bu} ({int(org_df[org_df['BUSINESS_UNIT']==bu]['HEADCOUNT'].sum())} people)"):
                bu_df=org_df[org_df["BUSINESS_UNIT"]==bu]
                for d in bu_df["DEPARTMENT"].dropna().unique():
                    d_df=bu_df[bu_df["DEPARTMENT"]==d]
                    st.markdown(f"**📁 {d}** ({int(d_df['HEADCOUNT'].sum())})")
                    for sd in d_df["SUB_DEPARTMENT"].dropna().unique():
                        sd_df=d_df[d_df["SUB_DEPARTMENT"]==sd]
                        st.markdown(f"&nbsp;&nbsp;&nbsp;└─ {sd} ({int(sd_df['HEADCOUNT'].sum())})")
                        for t in sd_df["TEAM"].dropna().unique():
                            cnt=int(sd_df[sd_df['TEAM']==t]['HEADCOUNT'].sum())
                            st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└─ {t} ({cnt})")

    st.subheader("Full Profile")
    ef2=q(f"SELECT * FROM {DB}.{SCH}.EMPLOYEE_FIELDS WHERE EMPLOYEE_ID={eid}")
    pii2=q(f"SELECT * FROM {DB}.{SCH}.EMPLOYEE_PII WHERE EMPLOYEE_ID={eid}")
    if len(ef2)>0 and len(pii2)>0:
        e2=ef2.iloc[0]
        p2=pii2.iloc[0]
        c1,c2,c3=st.columns(3)
        with c1:
            st.markdown("**Personal**")
            st.markdown(f"DOB: {e2['DATE_OF_BIRTH']}")
            st.markdown(f"Gender: {e2['GENDER']}")
            st.markdown(f"Blood Group: {e2['BLOOD_GROUP']}")
            st.markdown(f"Pronouns: {p2['PREFERRED_PRONOUNS']}")
            st.markdown(f"Marital: {p2['MARITAL_STATUS']}")
        with c2:
            st.markdown("**Contact**")
            st.markdown(f"Phone: {e2['PHONE']}")
            st.markdown(f"Personal Email: {e2['PERSONAL_EMAIL']}")
            st.markdown(f"Emergency: {e2['EMERGENCY_CONTACT_NAME']} ({e2['EMERGENCY_CONTACT_PHONE']})")
            st.markdown(f"Address: {p2['HOME_ADDRESS']}, {p2['CITY']}, {p2['STATE']} {p2['ZIP_CODE']}")
        with c3:
            st.markdown("**Employment**")
            st.markdown(f"Type: {e2['EMPLOYMENT_TYPE']}")
            st.markdown(f"Team: {e2['TEAM']}")
            st.markdown(f"Notice: {e2['NOTICE_PERIOD_DAYS']} days")
            st.markdown(f"Visa: {p2['VISA_STATUS']}")
            st.markdown(f"LinkedIn: {p2['LINKEDIN_URL']}")


# ===== TAB 13: PEOPLE DASHBOARD =====
with tab13:
    import altair as alt
    st.title("\U0001F465 People")
    st.caption("Click bars in charts to cross-filter \u2022 multi-select departments/BUs above")

    if "pending_pd_dept" in st.session_state:
        st.session_state.pd_dept_ms = st.session_state.pop("pending_pd_dept")

    f1,f2,f3,f4 = st.columns([2,2,1,1])
    bu_list = q(f"SELECT NAME FROM {DB}.{SCH}.BUSINESS_UNITS ORDER BY NAME")
    bu_multi = f1.multiselect("Business Units", bu_list["NAME"].tolist(), key="pd_bu_ms")
    dept_multi = f2.multiselect("Departments", sorted(employees_df["DEPARTMENT"].unique().tolist()), key="pd_dept_ms")
    year_sel = f3.selectbox("Year", [2026, 2025], key="pd_year")
    if f4.button("\U0001F504 Clear Filters", key="pd_clear"):
        st.session_state.pd_dept_ms = []
        st.session_state.pd_bu_ms = []
        st.rerun()

    bu_filter = "" if not bu_multi else " AND e.BUSINESS_UNIT_ID IN (SELECT BU_ID FROM " + DB + "." + SCH + ".BUSINESS_UNITS WHERE NAME IN (" + ",".join([f"'{x}'" for x in bu_multi]) + "))"
    dept_filter = "" if not dept_multi else " AND e.DEPARTMENT IN (" + ",".join([f"'{x}'" for x in dept_multi]) + ")"
    hp_bu_filter = "" if not bu_multi else " AND hp.BUSINESS_UNIT_ID IN (SELECT BU_ID FROM " + DB + "." + SCH + ".BUSINESS_UNITS WHERE NAME IN (" + ",".join([f"'{x}'" for x in bu_multi]) + "))"
    hp_dept_filter = "" if not dept_multi else " AND hp.DEPARTMENT IN (" + ",".join([f"'{x}'" for x in dept_multi]) + ")"

    match_df = q(f"""SELECT COUNT(*) AS CNT FROM {DB}.{SCH}.EMPLOYEE_360 e
        WHERE (e.TERMINATION_DATE IS NULL OR e.TERMINATION_DATE > CURRENT_DATE()){bu_filter}{dept_filter}""")
    matched_emp = int(match_df.iloc[0]["CNT"]) if len(match_df)>0 else 0

    if bu_multi or dept_multi:
        active = []
        if bu_multi: active.append(f"BU: {', '.join(bu_multi)}")
        if dept_multi: active.append(f"Dept: {', '.join(dept_multi)}")
        st.info(f"\U0001F50D Filters active \u2014 {' | '.join(active)} \u2014 **Matched:** {matched_emp} employees")
    else:
        st.caption(f"Showing all {matched_emp} active employees")

    st.markdown("### Work Force")
    wf_df = q(f"""SELECT COALESCE(ef.EMPLOYMENT_TYPE,'Full-time') AS TYPE, COUNT(*) AS CNT
        FROM {DB}.{SCH}.EMPLOYEE_360 e LEFT JOIN {DB}.{SCH}.EMPLOYEE_FIELDS ef ON e.EMPLOYEE_ID=ef.EMPLOYEE_ID
        WHERE (e.TERMINATION_DATE IS NULL OR e.TERMINATION_DATE > CURRENT_DATE()){bu_filter}{dept_filter}
        GROUP BY TYPE""")
    wf_map = dict(zip(wf_df["TYPE"], wf_df["CNT"]))
    total_wf = sum(wf_map.values())
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("EOM Headcount", total_wf)
    c2.metric("FTE", int(wf_map.get("Full-time", 0)))
    c3.metric("Contractor", int(wf_map.get("Contractor", 0)))
    c4.metric("M-Workforce", int(wf_map.get("Managed Workforce", 0)))

    st.markdown("### Headcount by Department (click to filter)")
    dept_ct = q(f"""SELECT e.DEPARTMENT, COUNT(*) AS HEADCOUNT FROM {DB}.{SCH}.EMPLOYEE_360 e
        WHERE (e.TERMINATION_DATE IS NULL OR e.TERMINATION_DATE > CURRENT_DATE()){bu_filter}
        GROUP BY e.DEPARTMENT ORDER BY HEADCOUNT DESC""")
    if len(dept_ct) > 0:
        sel1 = alt.selection_point(fields=["DEPARTMENT"], name="dept_sel")
        chart = alt.Chart(dept_ct).mark_bar().encode(
            x=alt.X("DEPARTMENT:N", sort="-y"),
            y=alt.Y("HEADCOUNT:Q"),
            color=alt.condition(sel1, alt.Color("DEPARTMENT:N", legend=None), alt.value("lightgray")),
            tooltip=["DEPARTMENT","HEADCOUNT"]
        ).add_params(sel1).properties(height=250)
        event = st.altair_chart(chart, on_select="rerun", key="dept_bar_chart")
        sel_data = event.selection.get("dept_sel", []) if event and event.selection else []
        if sel_data:
            clicked = [p.get("DEPARTMENT") for p in sel_data if p.get("DEPARTMENT")]
            if clicked and sorted(clicked) != sorted(st.session_state.get("pd_dept_ms", [])):
                st.session_state["pending_pd_dept"] = clicked
                st.rerun()

    st.markdown("### Actual vs Planned Headcount")
    ap_df = q(f"""
        WITH months AS (SELECT DATEADD('month', -seq, DATE_TRUNC('MONTH', CURRENT_DATE()))::DATE AS M
            FROM (SELECT ROW_NUMBER() OVER(ORDER BY SEQ4())-1 AS seq FROM TABLE(GENERATOR(ROWCOUNT=>12)))),
        actual AS (SELECT m.M AS MONTH,
            COUNT(CASE WHEN e.HIRE_DATE <= LAST_DAY(m.M) AND (e.TERMINATION_DATE IS NULL OR e.TERMINATION_DATE > LAST_DAY(m.M)) THEN 1 END) AS ACTUAL
            FROM months m CROSS JOIN {DB}.{SCH}.EMPLOYEE_360 e WHERE 1=1{bu_filter}{dept_filter} GROUP BY m.M),
        planned AS (SELECT DATE_TRUNC('MONTH', hp.MONTH)::DATE AS MONTH, SUM(hp.PLANNED_FTE+hp.PLANNED_CONTRACTORS+hp.PLANNED_MANAGED) AS PLANNED
            FROM {DB}.{SCH}.HEADCOUNT_PLAN hp WHERE 1=1{hp_bu_filter}{hp_dept_filter} GROUP BY MONTH)
        SELECT a.MONTH, a.ACTUAL, COALESCE(p.PLANNED, 0) AS PLANNED
        FROM actual a LEFT JOIN planned p ON a.MONTH=p.MONTH ORDER BY a.MONTH""")
    if len(ap_df)>0:
        ch = ap_df.copy()
        ch["MONTH"] = pd.to_datetime(ch["MONTH"])
        st.line_chart(ch.set_index("MONTH")[["ACTUAL","PLANNED"]])

    st.markdown("### Joiners vs Leavers")
    jl_df = q(f"""
        WITH months AS (SELECT DATEADD('month', -seq, DATE_TRUNC('MONTH', CURRENT_DATE()))::DATE AS M
            FROM (SELECT ROW_NUMBER() OVER(ORDER BY SEQ4())-1 AS seq FROM TABLE(GENERATOR(ROWCOUNT=>12)))),
        joiners AS (SELECT DATE_TRUNC('MONTH', e.HIRE_DATE)::DATE AS MONTH, COUNT(*) AS JOINERS
            FROM {DB}.{SCH}.EMPLOYEE_360 e WHERE e.HIRE_DATE >= DATEADD('month',-12,CURRENT_DATE()){bu_filter}{dept_filter} GROUP BY MONTH),
        leavers AS (SELECT DATE_TRUNC('MONTH', e.TERMINATION_DATE)::DATE AS MONTH, COUNT(*) AS LEAVERS
            FROM {DB}.{SCH}.EMPLOYEE_360 e WHERE e.TERMINATION_DATE IS NOT NULL AND e.TERMINATION_DATE >= DATEADD('month',-12,CURRENT_DATE()){bu_filter}{dept_filter} GROUP BY MONTH)
        SELECT m.M AS MONTH, COALESCE(j.JOINERS,0) AS JOINERS, -COALESCE(l.LEAVERS,0) AS LEAVERS
        FROM months m LEFT JOIN joiners j ON m.M=j.MONTH LEFT JOIN leavers l ON m.M=l.MONTH ORDER BY m.M""")
    if len(jl_df)>0:
        c1,c2,c3 = st.columns(3)
        c1.metric("Total Joiners (12mo)", int(jl_df["JOINERS"].sum()))
        c2.metric("Total Leavers (12mo)", int(-jl_df["LEAVERS"].sum()))
        c3.metric("Net Change", int(jl_df["JOINERS"].sum() + jl_df["LEAVERS"].sum()))
        ch = jl_df.copy()
        ch["MONTH"] = pd.to_datetime(ch["MONTH"])
        st.bar_chart(ch.set_index("MONTH")[["JOINERS","LEAVERS"]], color=["#2196F3","#F44336"])

    st.markdown("### Attrition - FTE (Quarterly)")
    att_df = q(f"""SELECT 'Q'||QUARTER(e.TERMINATION_DATE)::VARCHAR||' '||YEAR(e.TERMINATION_DATE)::VARCHAR AS QUARTER,
        COUNT(*) AS LEAVERS, ROUND(COUNT(*) * 100.0 / NULLIF({max(matched_emp, 1)}, 0), 1) AS ATTRITION_PCT
        FROM {DB}.{SCH}.EMPLOYEE_360 e WHERE e.TERMINATION_DATE IS NOT NULL AND e.TERMINATION_DATE >= DATEADD('month',-12,CURRENT_DATE()){bu_filter}{dept_filter}
        GROUP BY QUARTER ORDER BY MIN(e.TERMINATION_DATE)""")
    if len(att_df)>0:
        st.bar_chart(att_df.set_index("QUARTER")["ATTRITION_PCT"])

    st.markdown("### Internal Training % of Total Logged Hours")
    tr_df = q(f"""SELECT DATE_TRUNC('MONTH', te.SPENT_DATE)::DATE AS MONTH,
        ROUND(SUM(CASE WHEN t.TASK_NAME IN ('Training','Meeting') THEN te.HOURS ELSE 0 END) * 100.0 / NULLIF(SUM(te.HOURS),0), 2) AS TRAINING_PCT
        FROM {DB}.{SCH}.TIME_ENTRIES te JOIN {DB}.{SCH}.TASKS t ON te.TASK_ID=t.TASK_ID
        JOIN {DB}.{SCH}.EMPLOYEE_360 e ON te.EMPLOYEE_ID=e.EMPLOYEE_ID
        WHERE te.SPENT_DATE >= DATEADD('month',-12,CURRENT_DATE()){bu_filter}{dept_filter}
        GROUP BY MONTH ORDER BY MONTH""")
    if len(tr_df)>0:
        ch = tr_df.copy()
        ch["MONTH"] = pd.to_datetime(ch["MONTH"])
        st.bar_chart(ch.set_index("MONTH")["TRAINING_PCT"])

# ===== TAB 14: PERFORMANCE DASHBOARD =====
with tab14:
    import altair as alt
    st.title("\U0001F4CA Performance")
    st.caption("Click bars in charts to cross-filter \u2022 multi-select departments/BUs above")

    if "pending_pf_dept" in st.session_state:
        st.session_state.pf_dept_ms = st.session_state.pop("pending_pf_dept")

    f1,f2,f3,f4 = st.columns([2,2,1,1])
    bu_multi2 = f1.multiselect("Business Units", bu_list["NAME"].tolist(), key="pf_bu_ms")
    dept_multi2 = f2.multiselect("Departments", sorted(employees_df["DEPARTMENT"].unique().tolist()), key="pf_dept_ms")
    year_sel2 = f3.selectbox("Year", [2026, 2025], key="pf_year")
    if f4.button("\U0001F504 Clear Filters", key="pf_clear"):
        st.session_state.pf_dept_ms = []
        st.session_state.pf_bu_ms = []
        st.rerun()

    bu_filter2 = "" if not bu_multi2 else " AND e.BUSINESS_UNIT_ID IN (SELECT BU_ID FROM " + DB + "." + SCH + ".BUSINESS_UNITS WHERE NAME IN (" + ",".join([f"'{x}'" for x in bu_multi2]) + "))"
    dept_filter2 = "" if not dept_multi2 else " AND e.DEPARTMENT IN (" + ",".join([f"'{x}'" for x in dept_multi2]) + ")"

    match_df2 = q(f"""SELECT COUNT(DISTINCT e.EMPLOYEE_ID) AS EMPS,
        COUNT(DISTINCT CASE WHEN p.STATUS='Active' THEN p.PROJECT_ID END) AS ACTIVE_PROJ
        FROM {DB}.{SCH}.EMPLOYEE_360 e
        LEFT JOIN {DB}.{SCH}.PROJECT_ASSIGNMENTS pa ON e.EMPLOYEE_ID=pa.EMPLOYEE_ID
        LEFT JOIN {DB}.{SCH}.PROJECTS p ON pa.PROJECT_ID=p.PROJECT_ID
        WHERE (e.TERMINATION_DATE IS NULL OR e.TERMINATION_DATE > CURRENT_DATE()){bu_filter2}{dept_filter2}""")
    me = int(match_df2.iloc[0]["EMPS"]) if len(match_df2)>0 else 0
    mp = int(match_df2.iloc[0]["ACTIVE_PROJ"]) if len(match_df2)>0 else 0

    if bu_multi2 or dept_multi2:
        active2 = []
        if bu_multi2: active2.append(f"BU: {', '.join(bu_multi2)}")
        if dept_multi2: active2.append(f"Dept: {', '.join(dept_multi2)}")
        st.info(f"\U0001F50D Filters active \u2014 {' | '.join(active2)} \u2014 **Matched:** {me} employees \u2022 {mp} active projects")
    else:
        st.caption(f"Showing all {me} active employees \u2022 {mp} active projects")

    st.markdown("### Utilization")
    util_card = q(f"""
        WITH mtd AS (SELECT SUM(te.HOURS) AS TOTAL_HRS, SUM(CASE WHEN te.IS_BILLABLE THEN te.HOURS ELSE 0 END) AS BILLABLE_HRS
            FROM {DB}.{SCH}.TIME_ENTRIES te JOIN {DB}.{SCH}.EMPLOYEE_360 e ON te.EMPLOYEE_ID=e.EMPLOYEE_ID
            WHERE DATE_TRUNC('MONTH', te.SPENT_DATE) = DATE_TRUNC('MONTH', CURRENT_DATE()){bu_filter2}{dept_filter2}),
        ytd AS (SELECT SUM(te.HOURS) AS TOTAL_HRS, SUM(CASE WHEN te.IS_BILLABLE THEN te.HOURS ELSE 0 END) AS BILLABLE_HRS
            FROM {DB}.{SCH}.TIME_ENTRIES te JOIN {DB}.{SCH}.EMPLOYEE_360 e ON te.EMPLOYEE_ID=e.EMPLOYEE_ID
            WHERE YEAR(te.SPENT_DATE)={year_sel2}{bu_filter2}{dept_filter2})
        SELECT ROUND(mtd.BILLABLE_HRS/NULLIF(mtd.TOTAL_HRS,0)*100, 1) AS MTD_GROSS,
            ROUND(mtd.BILLABLE_HRS/NULLIF(mtd.TOTAL_HRS,0)*100*1.08, 1) AS MTD_NET, 93.0 AS MTD_AVAIL,
            ROUND(ytd.BILLABLE_HRS/NULLIF(ytd.TOTAL_HRS,0)*100, 1) AS YTD_GROSS,
            ROUND(ytd.BILLABLE_HRS/NULLIF(ytd.TOTAL_HRS,0)*100*1.08, 1) AS YTD_NET, 93.1 AS YTD_AVAIL
        FROM mtd, ytd""")
    if len(util_card)>0:
        u = util_card.iloc[0]
        c1,c2,c3 = st.columns(3)
        c1.metric("MTD Gross", f"{u['MTD_GROSS']:.1f}%" if pd.notna(u['MTD_GROSS']) else "N/A")
        c2.metric("MTD Net", f"{u['MTD_NET']:.1f}%" if pd.notna(u['MTD_NET']) else "N/A")
        c3.metric("MTD Availability", f"{u['MTD_AVAIL']:.1f}%")
        c1,c2,c3 = st.columns(3)
        c1.metric("YTD Gross", f"{u['YTD_GROSS']:.1f}%" if pd.notna(u['YTD_GROSS']) else "N/A")
        c2.metric("YTD Net", f"{u['YTD_NET']:.1f}%" if pd.notna(u['YTD_NET']) else "N/A")
        c3.metric("YTD Availability", f"{u['YTD_AVAIL']:.1f}%")

    st.markdown("---")
    col_rev, col_bench = st.columns(2)
    with col_rev:
        st.markdown("### This Month Revenue")
        rev_df = q(f"""SELECT ROUND(SUM(te.HOURS * p.HOURLY_RATE), 0) AS MTD_HARVEST, ROUND(SUM(te.HOURS), 1) AS TOTAL_HOURS
            FROM {DB}.{SCH}.TIME_ENTRIES te JOIN {DB}.{SCH}.PROJECTS p ON te.PROJECT_ID=p.PROJECT_ID
            JOIN {DB}.{SCH}.EMPLOYEE_360 e ON te.EMPLOYEE_ID=e.EMPLOYEE_ID
            WHERE te.IS_BILLABLE=TRUE AND DATE_TRUNC('MONTH', te.SPENT_DATE)=DATE_TRUNC('MONTH', CURRENT_DATE()){bu_filter2}{dept_filter2}""")
        if len(rev_df)>0 and pd.notna(rev_df.iloc[0]["MTD_HARVEST"]):
            r = rev_df.iloc[0]
            total_hrs = r["TOTAL_HOURS"] if r["TOTAL_HOURS"] else 1
            rev = r["MTD_HARVEST"]
            st.metric("MTD Harvest Revenue", f"${rev/1000000:.2f}M")
            st.metric("Projected", f"${(rev*1.05)/1000000:.2f}M")
            st.metric("Avg. Revenue Per Hour", f"${rev/total_hrs:.2f}")
        else:
            st.info("No billable hours in current filter scope.")

    with col_bench:
        st.markdown("### Bench")
        bench_df = q(f"""
            WITH alloc AS (SELECT e.EMPLOYEE_ID, COALESCE(SUM(CASE WHEN p.STATUS='Active' THEN pa.ALLOCATION_PCT END),0) AS ACTIVE_PCT
                FROM {DB}.{SCH}.EMPLOYEE_360 e
                LEFT JOIN {DB}.{SCH}.PROJECT_ASSIGNMENTS pa ON e.EMPLOYEE_ID=pa.EMPLOYEE_ID
                LEFT JOIN {DB}.{SCH}.PROJECTS p ON pa.PROJECT_ID=p.PROJECT_ID
                WHERE (e.TERMINATION_DATE IS NULL OR e.TERMINATION_DATE > CURRENT_DATE()){bu_filter2}{dept_filter2}
                GROUP BY e.EMPLOYEE_ID)
            SELECT COUNT(CASE WHEN ACTIVE_PCT < 50 THEN 1 END) AS BENCH_COUNT,
                ROUND(SUM(CASE WHEN ACTIVE_PCT < 100 THEN (100-ACTIVE_PCT)/100.0 * 40 END), 1) AS AVAIL_HRS,
                ROUND(SUM(CASE WHEN ACTIVE_PCT < 50 THEN (100-ACTIVE_PCT)/100.0 * 40 * 150 END) / 1000000, 2) AS BENCH_VALUE_M FROM alloc""")
        if len(bench_df)>0:
            b = bench_df.iloc[0]
            st.metric("Total Bench", int(b["BENCH_COUNT"]) if pd.notna(b["BENCH_COUNT"]) else 0)
            st.metric("Availability (hrs/wk)", f"{b['AVAIL_HRS']:.1f}" if pd.notna(b["AVAIL_HRS"]) else "0")
            st.metric("Bench Value", f"${b['BENCH_VALUE_M']:.2f}M" if pd.notna(b["BENCH_VALUE_M"]) else "$0")

    st.markdown("### Revenue by Department (click to filter)")
    rev_dept = q(f"""SELECT e.DEPARTMENT, ROUND(SUM(te.HOURS * p.HOURLY_RATE)/1000, 0) AS REVENUE_K
        FROM {DB}.{SCH}.TIME_ENTRIES te JOIN {DB}.{SCH}.PROJECTS p ON te.PROJECT_ID=p.PROJECT_ID
        JOIN {DB}.{SCH}.EMPLOYEE_360 e ON te.EMPLOYEE_ID=e.EMPLOYEE_ID
        WHERE te.IS_BILLABLE=TRUE AND te.SPENT_DATE >= DATEADD('month',-3,CURRENT_DATE()){bu_filter2}
        GROUP BY e.DEPARTMENT ORDER BY REVENUE_K DESC""")
    if len(rev_dept)>0:
        sel2 = alt.selection_point(fields=["DEPARTMENT"], name="rev_sel")
        chart2 = alt.Chart(rev_dept).mark_bar().encode(
            x=alt.X("DEPARTMENT:N", sort="-y"),
            y=alt.Y("REVENUE_K:Q", title="Revenue (Last 3mo, $K)"),
            color=alt.condition(sel2, alt.Color("DEPARTMENT:N", legend=None), alt.value("lightgray")),
            tooltip=["DEPARTMENT","REVENUE_K"]
        ).add_params(sel2).properties(height=250)
        event2 = st.altair_chart(chart2, on_select="rerun", key="rev_dept_chart")
        sel_data2 = event2.selection.get("rev_sel", []) if event2 and event2.selection else []
        if sel_data2:
            clicked = [p.get("DEPARTMENT") for p in sel_data2 if p.get("DEPARTMENT")]
            if clicked and sorted(clicked) != sorted(st.session_state.get("pf_dept_ms", [])):
                st.session_state["pending_pf_dept"] = clicked
                st.rerun()

    st.markdown("### Monthly Utilization")
    mu_df = q(f"""SELECT DATE_TRUNC('MONTH', te.SPENT_DATE)::DATE AS MONTH,
        ROUND(SUM(CASE WHEN te.IS_BILLABLE THEN te.HOURS ELSE 0 END)/NULLIF(SUM(te.HOURS),0)*100, 1) AS GROSS,
        ROUND(SUM(CASE WHEN te.IS_BILLABLE THEN te.HOURS ELSE 0 END)/NULLIF(SUM(te.HOURS),0)*100*1.08, 1) AS NET,
        93.0 AS AVAILABILITY, 80.0 AS TARGET_GROSS
        FROM {DB}.{SCH}.TIME_ENTRIES te JOIN {DB}.{SCH}.EMPLOYEE_360 e ON te.EMPLOYEE_ID=e.EMPLOYEE_ID
        WHERE te.SPENT_DATE >= DATEADD('month',-9,CURRENT_DATE()){bu_filter2}{dept_filter2} GROUP BY MONTH ORDER BY MONTH""")
    if len(mu_df)>0:
        ch = mu_df.copy()
        ch["MONTH"] = pd.to_datetime(ch["MONTH"])
        st.line_chart(ch.set_index("MONTH")[["GROSS","NET","AVAILABILITY","TARGET_GROSS"]])

    st.markdown("### Weekly Utilization")
    wu_df = q(f"""SELECT DATE_TRUNC('WEEK', te.SPENT_DATE)::DATE AS WEEK,
        ROUND(SUM(CASE WHEN te.IS_BILLABLE THEN te.HOURS ELSE 0 END)/NULLIF(SUM(te.HOURS),0)*100, 1) AS GROSS,
        ROUND(SUM(CASE WHEN te.IS_BILLABLE THEN te.HOURS ELSE 0 END)/NULLIF(SUM(te.HOURS),0)*100*1.08, 1) AS NET,
        93.0 AS AVAILABILITY, 80.0 AS TARGET_GROSS
        FROM {DB}.{SCH}.TIME_ENTRIES te JOIN {DB}.{SCH}.EMPLOYEE_360 e ON te.EMPLOYEE_ID=e.EMPLOYEE_ID
        WHERE te.SPENT_DATE >= DATEADD('week',-12,CURRENT_DATE()){bu_filter2}{dept_filter2} GROUP BY WEEK ORDER BY WEEK""")
    if len(wu_df)>0:
        ch = wu_df.copy()
        ch["WEEK"] = pd.to_datetime(ch["WEEK"])
        st.line_chart(ch.set_index("WEEK")[["GROSS","NET","AVAILABILITY","TARGET_GROSS"]])


# ===== TAB: ASK YOUR DATA (Cortex Analyst) =====
with tab_analyst:
    import _snowflake
    st.title("\U0001F4AC Ask Your Data")
    st.caption("Natural-language analytics over the GOLD layer via Snowflake Cortex Analyst "
               "(semantic model: GOLD.HR_ANALYST). Ask about headcount, utilization, salaries, leave or recruiting.")
    SEMANTIC_VIEW = f"{DB}.{SCH}.HR_ANALYST"

    if "analyst_msgs" not in st.session_state:
        st.session_state.analyst_msgs = []

    ex_cols = st.columns(3)
    ex_qs = ["Headcount by department", "Billable % by business unit", "Average salary by team"]
    for i, exq in enumerate(ex_qs):
        if ex_cols[i].button(exq, key=f"analyst_ex_{i}"):
            st.session_state.analyst_pending = exq

    for m in st.session_state.analyst_msgs:
        with st.chat_message(m["role"]):
            if m.get("text"):
                st.markdown(m["text"])
            if m.get("sql"):
                with st.expander("Generated SQL"):
                    st.code(m["sql"], language="sql")
            dfr = m.get("df")
            if dfr is not None and len(dfr) > 0:
                st.dataframe(dfr, use_container_width=True, hide_index=True)
                if dfr.shape[1] == 2 and pd.api.types.is_numeric_dtype(dfr.iloc[:, 1]):
                    try:
                        st.bar_chart(dfr.set_index(dfr.columns[0]))
                    except Exception:
                        pass

    user_q = st.chat_input("Ask about headcount, utilization, salaries, leave...") \
        or st.session_state.pop("analyst_pending", None)

    if user_q:
        st.session_state.analyst_msgs.append({"role": "user", "text": user_q})
        with st.spinner("Cortex Analyst is thinking..."):
            answer_text, sql_stmt = "", None
            try:
                req_body = {"messages": [{"role": "user", "content": [{"type": "text", "text": user_q}]}],
                            "semantic_view": SEMANTIC_VIEW}
                resp = _snowflake.send_snow_api_request(
                    "POST", "/api/v2/cortex/analyst/message", {}, {}, req_body, None, 40000)
                if int(resp.get("status", 500)) < 400:
                    body = json.loads(resp["content"])
                    for item in body.get("message", {}).get("content", []):
                        if item.get("type") == "text":
                            answer_text += item.get("text", "")
                        elif item.get("type") == "sql":
                            sql_stmt = item.get("statement")
                else:
                    answer_text = f"Cortex Analyst returned status {resp.get('status')}: {str(resp.get('content'))[:300]}"
            except Exception as e:
                answer_text = f"Could not reach Cortex Analyst: {e}"

            result_df = None
            if sql_stmt:
                try:
                    result_df = session.sql(sql_stmt).to_pandas()
                except Exception as e:
                    answer_text += f"\n\n_Generated SQL did not run: {e}_"

            st.session_state.analyst_msgs.append({
                "role": "assistant",
                "text": answer_text or "_(no response)_",
                "sql": sql_stmt,
                "df": result_df,
            })
        st.rerun()
