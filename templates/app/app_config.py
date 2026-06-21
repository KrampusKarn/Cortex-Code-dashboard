"""DEFAULT app config — render.py OVERWRITES this from a schema_spec at scaffold time.

Kept here with sane defaults so the template dir is importable/lintable standalone.
The Streamlit app reads identity ONLY from this module — never inline literals.
"""
DATABASE          = "DEMO_APP"
SCHEMA            = "PUBLIC"
SERVICE_FQN       = "DEMO_APP.PUBLIC.COMPANY_KB_SEARCH"
KB_TABLE          = "COMPANY_KNOWLEDGE_BASE"
KB_CONTENT_COL    = "CONTENT"
LLM_MODEL         = "mistral-large2"
COMPANY_NAME      = "Acme Solutions Inc"
APP_TITLE         = "Demo Dashboard"
APP_ICON          = "📊"
ASSISTANT_INTRO   = "Ask me about company info, benefits, and events."
CHAT_PLACEHOLDER  = "Ask a question..."
SUGGESTED_PROMPTS = ["What health plans do we offer?", "Upcoming events?", "PTO policy?"]
SEARCH_COLUMNS    = ["CONTENT", "TITLE", "CATEGORY"]
SEARCH_LIMIT      = 3
