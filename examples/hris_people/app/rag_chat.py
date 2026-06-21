"""Source-agnostic Cortex RAG chat assistant.

Retrieval-augmented chat over a Cortex Search service, with per-user multi-session
persistence in CHAT_SESSIONS / CHAT_MESSAGES.

  retrieve  →  SNOWFLAKE.CORTEX.SEARCH_PREVIEW(service, json_query)
  ground    →  build a prompt from the retrieved documents
  generate  →  SNOWFLAKE.CORTEX.COMPLETE(model, prompt)
  persist   →  parameterized INSERT/UPDATE (no string interpolation of user/LLM text)

Everything domain-specific (service, model, company name, prompts) is read from
the `cfg` module — call `render(session, cfg)` and nothing else needs changing.

SECURITY: every write uses params=[...] bind variables. User input and
LLM-generated text are NEVER interpolated into SQL strings. Only trusted config
identifiers (DATABASE/SCHEMA) are formatted into statements.
"""
import json

import streamlit as st


def _df(session, sql, params=None):
    stmt = session.sql(sql, params=params) if params is not None else session.sql(sql)
    return stmt.to_pandas()


def _ensure_session(session, cfg, username):
    tbl = f"{cfg.DATABASE}.{cfg.SCHEMA}.CHAT_SESSIONS"
    sessions = _df(session,
                   f"SELECT SESSION_ID, SESSION_NAME FROM {tbl} WHERE USERNAME = ? ORDER BY LAST_ACTIVE DESC",
                   params=[username])
    if len(sessions) == 0:
        session.sql(f"INSERT INTO {tbl} (USERNAME, SESSION_NAME) VALUES (?, ?)",
                    params=[username, "Chat 1"]).collect()
        sessions = _df(session,
                       f"SELECT SESSION_ID, SESSION_NAME FROM {tbl} WHERE USERNAME = ? ORDER BY LAST_ACTIVE DESC",
                       params=[username])
    return sessions


def _retrieve(session, cfg, question):
    """Return (context_text, sources[]) from the Cortex Search service."""
    payload = json.dumps({"query": question, "columns": cfg.SEARCH_COLUMNS, "limit": cfg.SEARCH_LIMIT})
    res = _df(session, "SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(?, ?) AS RESULTS",
              params=[cfg.SERVICE_FQN, payload])
    parts, sources = [], []
    if len(res):
        data = json.loads(res.iloc[0]["RESULTS"])
        for r in data.get("results", []):
            parts.append(r.get(cfg.KB_CONTENT_COL, "") or "")
            label = " — ".join(str(r.get(c)) for c in cfg.SEARCH_COLUMNS
                               if c != cfg.KB_CONTENT_COL and r.get(c))
            if label:
                sources.append(label)
    context = "\n\n---\n\n".join(p for p in parts if p) or "No relevant information found."
    return context, sources


def _answer(session, cfg, question, context):
    prompt = (
        f"You are a helpful assistant for {cfg.COMPANY_NAME}. "
        f"Answer the question using ONLY the context below. "
        f"If the answer is not in the context, say you don't have that information.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}\n\n"
        f"Answer in clear markdown with specific details."
    )
    df = _df(session, "SELECT SNOWFLAKE.CORTEX.COMPLETE(?, ?) AS ANSWER",
             params=[cfg.LLM_MODEL, prompt])
    return df.iloc[0]["ANSWER"] if len(df) else "Sorry, I could not generate a response."


def render(session, cfg):
    st.subheader(f"💬 {cfg.APP_TITLE} Assistant")
    st.caption(cfg.ASSISTANT_INTRO)

    username = session.sql("SELECT CURRENT_USER() AS U").to_pandas().iloc[0]["U"]
    msgs_tbl = f"{cfg.DATABASE}.{cfg.SCHEMA}.CHAT_MESSAGES"
    sess_tbl = f"{cfg.DATABASE}.{cfg.SCHEMA}.CHAT_SESSIONS"

    sessions = _ensure_session(session, cfg, username)
    id_by_name = dict(zip(sessions["SESSION_NAME"], sessions["SESSION_ID"]))

    top = st.columns([4, 1])
    chosen_name = top[0].selectbox("Conversation", list(id_by_name.keys()), key="rag_active_name")
    if top[1].button("➕ New chat", key="rag_new"):
        n = len(sessions) + 1
        session.sql(f"INSERT INTO {sess_tbl} (USERNAME, SESSION_NAME) VALUES (?, ?)",
                    params=[username, f"Chat {n}"]).collect()
        st.rerun()
    active_id = int(id_by_name[chosen_name])

    # history
    history = _df(session,
                  f"SELECT ROLE, CONTENT, SOURCES FROM {msgs_tbl} "
                  f"WHERE SESSION_ID = ? AND USERNAME = ? ORDER BY CREATED_AT",
                  params=[active_id, username])
    for _, m in history.iterrows():
        with st.chat_message("user" if m["ROLE"] == "user" else "assistant"):
            st.markdown(m["CONTENT"])
            if m["ROLE"] == "assistant" and m["SOURCES"]:
                try:
                    srcs = json.loads(m["SOURCES"])
                except (TypeError, ValueError):
                    srcs = []
                if srcs:
                    with st.expander("Sources"):
                        for s in srcs:
                            st.markdown(f"- {s}")

    # suggested prompts (only when the conversation is empty)
    pending = st.session_state.pop("rag_pending", None)
    if len(history) == 0 and not pending:
        cols = st.columns(len(cfg.SUGGESTED_PROMPTS))
        for i, p in enumerate(cfg.SUGGESTED_PROMPTS):
            if cols[i].button(p, key=f"rag_sugg_{i}"):
                st.session_state["rag_pending"] = p
                st.rerun()

    user_q = st.chat_input(cfg.CHAT_PLACEHOLDER) or pending
    if not user_q:
        return

    # 1) persist the user's message (parameterized)
    session.sql(f"INSERT INTO {msgs_tbl} (SESSION_ID, USERNAME, ROLE, CONTENT, SOURCES) "
                f"VALUES (?, ?, 'user', ?, NULL)",
                params=[active_id, username, user_q]).collect()

    # 2) retrieve + 3) generate
    with st.spinner("Thinking…"):
        context, sources = _retrieve(session, cfg, user_q)
        answer = _answer(session, cfg, user_q, context)

    # 4) persist the assistant message + touch the session (parameterized)
    session.sql(f"INSERT INTO {msgs_tbl} (SESSION_ID, USERNAME, ROLE, CONTENT, SOURCES) "
                f"VALUES (?, ?, 'assistant', ?, ?)",
                params=[active_id, username, answer, json.dumps(sources)]).collect()
    session.sql(f"UPDATE {sess_tbl} SET LAST_ACTIVE = CURRENT_TIMESTAMP() WHERE SESSION_ID = ?",
                params=[active_id]).collect()
    st.rerun()
