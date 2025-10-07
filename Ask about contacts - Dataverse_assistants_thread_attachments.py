# -*- coding: utf-8 -*-
"""
Dynamics 365 • Contact Assistant (Responses API + Code Interpreter)

- Replaces deprecated Assistants API with the Responses API (no deprecation warnings).
- Uploads the contacts CSV once; uses Code Interpreter with an auto container and file_ids.
- Preserves chat context via previous_response_id.
- Reads secrets from st.secrets or environment variables.
"""

import os
import io
import time
import warnings
from typing import Optional

import requests
import pandas as pd
import streamlit as st
from openai import OpenAI

# -----------------------------------------
# Page & App Config
# -----------------------------------------
st.set_page_config(
    page_title="Dynamics 365 • Contact Assistant",
    page_icon="📇",
    layout="wide",
)

# Fluent / D365 color tokens
D365_COLORS = {
    "primary": "#0078D4",  # Fluent primary blue
    "primaryDark": "#106EBE",
    "neutralBg": "#F3F2F1",  # Neutral 98
    "neutral": "#201F1E",
    "border": "#E1DFDD",
    "success": "#107C10",
    "danger": "#A80000",
    "black": "#000000",
    "white": "#FFFFFF",
    "activeBg": "#F3F2F1",  # light grey for active nav button
    "activeBorder": "#0078D4",  # blue border for active nav button
}

# -----------------------------------------
# D365 / Entra settings (replace with your values or use st.secrets / env)
# -----------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
RESOURCE = os.getenv("D365_RESOURCE", "https://squadd365.crm8.dynamics.com")

# -----------------------------------------
# Helpers: secrets & client
# -----------------------------------------
def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """Prefer Streamlit secrets; fallback to env var."""
    try:
        val = st.secrets.get(name, None)
    except Exception:
        val = None
    return val if val is not None else os.getenv(name, default)

def make_openai_client() -> Optional[OpenAI]:
    """
    Prefer Azure OpenAI if both endpoint and key are present; otherwise use OpenAI public.
    Azure Responses API uses base_url: https://<res>.openai.azure.com/openai/v1/
    """
    aoai_endpoint = (get_secret("AZURE_OPENAI_ENDPOINT") or "").rstrip("/")
    aoai_key = get_secret("AZURE_OPENAI_API_KEY")
    if aoai_endpoint and aoai_key:
        return OpenAI(
            api_key=aoai_key,
            base_url=f"{aoai_endpoint}/openai/v1/",
        )
    api_key = get_secret("OPENAI_API_KEY") or OPENAI_API_KEY
    if api_key:
        return OpenAI(api_key=api_key)
    return None

# Initialize client (Azure first, then public OpenAI)
#client = make_openai_client()
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# -----------------------------------------
# Branding
# -----------------------------------------
ORG_NAME = get_secret("ORG_NAME", "Squad software Pvt Ltd")
USER_DISPLAY_NAME = get_secret("USER_DISPLAY_NAME", "You")
USER_INITIALS = "".join([s[0] for s in USER_DISPLAY_NAME.split()][:2]).upper() or "U"

CONTACTS_API = f"{RESOURCE}/api/data/v9.2/contacts?$select=fullname,emailaddress1,telephone1,address1_city"
QUERYLOG_API = f"{RESOURCE}/api/data/v9.2/new_querylogs"

# =============================
# Global CSS (Pinned Sidebar, Black Strip at Top, Nav Button Styles, Hide Deploy UI)
# =============================
st.markdown(
    f"""
<style>
:root {{
  --primary: {D365_COLORS['primary']};
  --primaryDark: {D365_COLORS['primaryDark']};
  --neutralBg: {D365_COLORS['neutralBg']};
  --neutral: {D365_COLORS['neutral']};
  --border: {D365_COLORS['border']};
  --success: {D365_COLORS['success']};
  --danger: {D365_COLORS['danger']};
  --black: {D365_COLORS['black']};
  --white: {D365_COLORS['white']};
  --activeBg: {D365_COLORS['activeBg']};
  --activeBorder: {D365_COLORS['activeBorder']};
}}
html, body, .stApp {{
  font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
  background: var(--neutralBg);
  margin: 0 !important; /* ensure no top gap */
  padding: 0 !important; /* ensure no top gap */
}}
/* Remove Streamlit header and top padding (kill white gap) */
header[data-testid="stHeader"] {{
  display: none !important;
}}
div[data-testid="stAppViewContainer"] {{
  padding-top: 0 !important;
  margin-top: 0 !important;
}}
section.main > div.block-container, div.block-container {{
  padding-top: 0 !important;
  margin-top: 0 !important;
}}
/* ===== Pin sidebar permanently ===== */
section[data-testid="stSidebar"] {{
  transform: none !important;
  visibility: visible !important;
  opacity: 1 !important;
  position: sticky !important;
  left: 0 !important;
  top: 0 !important;
  height: 100vh !important;
}}
/* Prevent responsive collapse on narrow widths */
@media (max-width: 1024px) {{
  section[data-testid="stSidebar"] {{
    transform: none !important;
    position: fixed !important;
    z-index: 999 !important;
  }}
  div[data-testid="stAppViewContainer"] {{
    margin-left: 18rem !important; /* adjust to your sidebar width if needed */
  }}
}}
/* Hide any controls that open/close the sidebar */
[data-testid="collapsedControl"],
button[title="Open sidebar"],
button[title="Close sidebar"],
button[aria-label*="sidebar"],
[data-testid="stSidebarNav"] button {{
  display: none !important;
}}
/* Black strip on top */
.crm-blackstrip {{
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--black);
  color: var(--white);
  padding: 8px 16px;
  display: flex; align-items: center; justify-content: space-between;
}}
.crm-blackstrip .left {{
  display: flex; align-items: center; gap: 12px;
  font-weight: 600; letter-spacing: .2px;
}}
.crm-blackstrip .right {{
  display: flex; align-items: center; gap: 10px;
}}
.crm-blackstrip .persona {{
  width: 28px; height: 28px;
  border-radius: 50%;
  background: #3a3a3a;
  color: var(--white);
  display: grid; place-items: center;
  font-size: 12px; font-weight: 600;
}}
/* Command row container */
.crm-command {{
  background: white;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin: 12px 0;
}}
/* Sidebar visual */
section[data-testid="stSidebar"] > div {{
  background: white !important;
  border-right: 1px solid var(--border);
}}
.crm-card {{
  background: white; border: 1px solid var(--border);
  border-radius: 8px; padding: 16px; margin-top: 8px;
}}
.crm-subtle {{
  color: #605E5C; font-size: 13px;
}}
/* Base button tweaks */
.stButton button {{
  border-radius: 6px;
  border: 1px solid var(--border);
  background: #FFFFFF;
  color: #323130;
}}
.stButton button:hover {{
  border-color: var(--primary);
}}
/* Active nav button styling (light grey with blue border) */
.navbtn.active .stButton button {{
  background: var(--activeBg) !important;
  border: 1.5px solid var(--activeBorder) !important;
  color: var(--activeBorder) !important;
}}
/* Dataframe container border-radius */
.element-container:has(.stDataFrame) > div {{
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}}
/* Hide Streamlit deploy/share UI */
[data-testid="stToolbar"], .stDeployButton, div[data-testid="stDecoration"] {{
  display: none !important;
}}
header button[kind="header"] {{ display: none !important; }}
</style>
""",
    unsafe_allow_html=True,
)

# Black strip (top)
st.markdown(
    f"""
<div class="crm-blackstrip">
  <div class="left">
    <span>Dynamics 365</span>
  </div>
  <div class="right">
    <span style="opacity:.85; font-size:13px;">{ORG_NAME}</span>
    <span class="persona" title="{USER_DISPLAY_NAME}">{USER_INITIALS}</span>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# -----------------------------------------
# Warnings
# -----------------------------------------
# You shouldn't see Assistants deprecation warnings anymore, but keep this guard anyway.
# warnings.filterwarnings(
#     "ignore", message=".*Assistants API is deprecated.*", category=DeprecationWarning
# )

# -----------------------------------------
# Token acquisition (cached)
# -----------------------------------------
@st.cache_resource(ttl=3300, show_spinner=False)
def get_access_token() -> str:
    if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET, RESOURCE]):
        raise RuntimeError("Missing Entra/D365 settings in secrets or env.")
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": f"{RESOURCE}/.default",
        "grant_type": "client_credentials",
    }
    r = requests.post(url, data=data)
    r.raise_for_status()
    return r.json()["access_token"]

# -----------------------------------------
# Fetch contacts from D365 (cached + 401 retry)
# -----------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def fetch_contacts_from_d365() -> pd.DataFrame:
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Accept": "application/json",
    }
    r = requests.get(CONTACTS_API, headers=headers)
    if r.status_code == 401:
        # clear token cache & retry once
        try:
            get_access_token.clear()
        except Exception:
            pass
        token = get_access_token()
        headers["Authorization"] = f"Bearer {token}"
        r = requests.get(CONTACTS_API, headers=headers)
    r.raise_for_status()
    data = r.json().get("value", [])
    df = pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame(columns=["FullName", "Email", "Phone", "City"])
    df = df.rename(
        columns={
            "fullname": "FullName",
            "emailaddress1": "Email",
            "telephone1": "Phone",
            "address1_city": "City",
        }
    )
    cols = [c for c in ["FullName", "Email", "Phone", "City"] if c in df.columns] + [
        c for c in df.columns if c not in ["FullName", "Email", "Phone", "City"]
    ]
    return df[cols]

# -----------------------------------------
# D365: Query log
# -----------------------------------------
def create_query_log_in_d365(user_query: str, gpt_result: str):
    try:
        token = get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }
        payload = {
            "new_userquery": (user_query or "")[:100],
            "new_userquery2": user_query or "",
            "new_gptresult": gpt_result or "",
        }
        r = requests.post(QUERYLOG_API, headers=headers, json=payload, timeout=30)
        if r.status_code not in (200, 201, 204):
            raise Exception(f"Failed to insert query log: {r.text}")
    except Exception as e:
        st.error(f"❌ Failed to log to D365: {str(e)}")

# -----------------------------------------
# Session state
# -----------------------------------------
if "df" not in st.session_state:
    st.session_state.df = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "nav" not in st.session_state:
    st.session_state.nav = "Contacts"
if "auto_log" not in st.session_state:
    st.session_state.auto_log = True

# Responses-specific
for key in ["dataset_file_id", "last_response_id"]:
    if key not in st.session_state:
        st.session_state[key] = None

# -----------------------------------------
# (PII masking removed) — upload the original dataset as-is
# -----------------------------------------

# -----------------------------------------
# Upload dataset once (Responses API)
# -----------------------------------------
def init_responses_with_dataset(df: pd.DataFrame):
    if client is None:
        raise RuntimeError("LLM client not initialized (missing API key).")

    # Clean up prior upload
    old_id = st.session_state.get("dataset_file_id")
    if old_id:
        try:
            client.files.delete(old_id)
        except Exception:
            pass

    # Upload original (unmasked) dataset to the model
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    csv_file = io.BytesIO(csv_bytes)
    csv_file.name = f"contacts_{int(time.time())}.csv"

    # Purpose 'assistants' is accepted for tool containers (file store)
    uploaded = client.files.create(file=csv_file, purpose="assistants")
    st.session_state.dataset_file_id = uploaded.id

    # Reset Responses state
    st.session_state.last_response_id = None
    st.session_state.chat_history = []

# -----------------------------------------
# Ask via Responses API + Code Interpreter tool
# -----------------------------------------
def ask_with_responses(user_query: str) -> str:
    if client is None:
        return "⚠️ OpenAI client not initialized."
    file_id = st.session_state.get("dataset_file_id")
    if not file_id:
        return "⚠️ Dataset not loaded yet. Go to **Contacts** and click **📥 Fetch / Refresh Contacts**."

    tools = [{
        "type": "code_interpreter",
        "container": {
            "type": "auto",
            "file_ids": [file_id],  # make the CSV available to the Python sandbox
        },
    }]

    instructions = (
        "Use the attached contacts CSV to answer questions. "
        "You are a helpful data assistant. Answer with clear explanations, insights, "
        "or summaries based strictly on the dataset provided. Do NOT return code or "
        "programming instructions. Plain text only."
        "When helpful, write & run Python (pandas). Prefer concise tables and bullet points."
    )

    kwargs = dict(
        model="gpt-4o-mini",
        tools=tools,
        instructions=instructions,
        input=user_query,
    )

    # Keep multi-turn context without sending a message history
    last_id = st.session_state.get("last_response_id")
    if last_id:
        kwargs["previous_response_id"] = last_id

    # Call Responses API
    resp = client.responses.create(**kwargs)

    # Save to continue context in the next turn
    st.session_state.last_response_id = resp.id

    # Convenience field (SDK) that combines textual output
    text = (getattr(resp, "output_text", None) or "").strip()
    return text or "ℹ️ No text response."

# =============================
# Top Command Row (Nav Buttons + Contextual Action)
# =============================
st.markdown('<div class="crm-command">', unsafe_allow_html=True)

nav_cols = st.columns([1, 1, 1, 4], vertical_alignment="center")

def nav_button(label: str, view_name: str, key: str):
    active = (st.session_state.nav == view_name)
    # Wrapper to style the active button
    st.markdown(
        f'<div class="navbtn {"active" if active else ""}" id="{key}-wrap">',
        unsafe_allow_html=True
    )
    clicked = st.button(label, key=key, width="stretch")
    st.markdown("</div>", unsafe_allow_html=True)
    return clicked

with nav_cols[0]:
    click_contacts = nav_button("Contacts", "Contacts", "nav_contacts_btn")
with nav_cols[1]:
    click_assistant = nav_button("Assistant", "Assistant", "nav_assistant_btn")
with nav_cols[2]:
    click_logs = nav_button("Logs", "Logs", "nav_logs_btn")

nav_changed = False
if click_contacts and st.session_state.nav != "Contacts":
    st.session_state.nav = "Contacts"; nav_changed = True
elif click_assistant and st.session_state.nav != "Assistant":
    st.session_state.nav = "Assistant"; nav_changed = True
elif click_logs and st.session_state.nav != "Logs":
    st.session_state.nav = "Logs"; nav_changed = True
if nav_changed:
    st.rerun()

fetch_clicked = False
clear_clicked = False
with nav_cols[3]:
    if st.session_state.nav == "Contacts":
        fetch_clicked = st.button("📥 Fetch / Refresh Contacts", key="fetch_top", width="stretch")
    elif st.session_state.nav == "Logs":
        clear_clicked = st.button("🧹 Clear Local Conversation", key="clear_top", width="stretch")
    else:
        st.empty()
st.markdown("</div>", unsafe_allow_html=True)

# -----------------------------------------
# Views
# -----------------------------------------
if st.session_state.nav == "Contacts":
    # Fetch handler
    if fetch_clicked:
        with st.spinner("Fetching contacts from D365..."):
            try:
                st.session_state.df = fetch_contacts_from_d365()
                st.success(f"Fetched {len(st.session_state.df)} contacts from D365.")
                if st.session_state.df is not None and not st.session_state.df.empty:
                    with st.spinner("Uploading dataset to the model and resetting context..."):
                        init_responses_with_dataset(st.session_state.df)
                    st.success("Assistant context is now bound to the latest dataset (older dataset forgotten).")
            except Exception as e:
                st.error(f"❌ Error fetching contacts: {str(e)}")

    st.markdown("## Contacts")

    # Filters above grid
    with st.expander("🔎 Filters", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            name_kw = st.text_input("Name contains", "")
        with col2:
            city_kw = st.text_input("City contains", "")
        with col3:
            email_kw = st.text_input("Email contains", "")

    # Grid
    if st.session_state.df is not None:
        df_view = st.session_state.df.copy()
        if name_kw:
            df_view = df_view[df_view["FullName"].fillna("").str.contains(name_kw, case=False, na=False)]
        if city_kw:
            df_view = df_view[df_view["City"].fillna("").str.contains(city_kw, case=False, na=False)]
        if email_kw:
            df_view = df_view[df_view["Email"].fillna("").str.contains(email_kw, case=False, na=False)]
        st.dataframe(df_view, width='stretch', height=420)
    else:
        st.info("Click **📥 Fetch / Refresh Contacts** above to load data from Dynamics 365.")

elif st.session_state.nav == "Assistant":
    st.markdown("## Assistant")
    if st.session_state.df is None or st.session_state.df.empty:
        st.warning("No contacts loaded yet. Go to **Contacts** and click **📥 Fetch / Refresh Contacts**.")
    else:
        # Render chat history
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        user_query = st.chat_input("Ask about the contacts (e.g., 'Top cities by contact count', 'How many contacts have email?')")
        if user_query:
            with st.chat_message("user"):
                st.write(user_query)
            with st.chat_message("assistant"):
                with st.spinner("Analyzing dataset with Code Interpreter..."):
                    result = ask_with_responses(user_query)
                st.write(result)

            # Record locally
            st.session_state.chat_history.append({"role": "user", "content": user_query})
            st.session_state.chat_history.append({"role": "assistant", "content": result})

            # Silent auto-log
            if st.session_state.auto_log:
                create_query_log_in_d365(user_query, result)

        # Hints
        st.markdown(
            """
            <div style="margin-top:8px"></div>
            <b>Try these</b><br/>
            • "Summarize contacts by city"<br/>
            • "List contacts with missing emails"<br/>
            • "Give me 5 sample contacts with name and city"<br/>
            • "Which email domains are most common?"
            """,
            unsafe_allow_html=True,
        )

elif st.session_state.nav == "Logs":
    if clear_clicked:
        st.session_state.chat_history = []
        st.session_state.last_response_id = None
        st.success("Cleared local conversation history.")
    st.markdown("## Logs")
    st.write("Recent conversation (local). Entries may also be written to the D365 entity (server-side).")
    if st.session_state.chat_history:
        with st.expander("Conversation History", expanded=True):
            for msg in st.session_state.chat_history:
                role = "User" if msg["role"] == "user" else "Assistant"
                st.markdown(f"**{role}:** {msg['content']}")
    else:
        st.info("No conversations yet. Go to **Assistant** and ask a question.")
