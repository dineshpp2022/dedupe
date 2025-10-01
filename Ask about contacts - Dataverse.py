import streamlit as st
import pandas as pd
import requests
import os
from openai import OpenAI

# =============================
# Page & App Styling (D365 look)
# =============================
st.set_page_config(
    page_title="Dynamics 365 • Contact Assistant",
    page_icon="📇",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Fluent / D365 color tokens
D365_COLORS = {
    "primary": "#0078D4",   # Fluent primary blue
    "primaryDark": "#106EBE",
    "neutralBg": "#F3F2F1", # Neutral 98
    "neutral": "#201F1E",
    "border": "#E1DFDD",
    "success": "#107C10",
    "danger": "#A80000",
    "black": "#000000",
    "white": "#FFFFFF",
    "activeBg": "#F3F2F1",   # light grey for active button
    "activeBorder": "#0078D4" # blue border for active button
}

# Organization & Persona
ORG_NAME = os.getenv("ORG_NAME", "Squad Software Pvt Ltd")
USER_DISPLAY_NAME = os.getenv("USER_DISPLAY_NAME", "You")
USER_INITIALS = "".join([s[0] for s in USER_DISPLAY_NAME.split()][:2]).upper() or "U"

# -----------------------------
# CSS — black strip & CRM-like UI; hide Deploy; custom nav button styles
# + remove top white gap so content starts right under browser address bar
# -----------------------------
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
        }}

        /* Remove Streamlit header and top padding (kill white gap) */
        header[data-testid="stHeader"] {{
            display: none !important;
        }}
        /* Remove any residual top padding/margin so strip hits the top */
        div[data-testid="stAppViewContainer"] {{
            padding-top: 0 !important;
            margin-top: 0 !important;
        }}
        section.main > div.block-container, div.block-container {{
            padding-top: 0 !important;
            margin-top: 0 !important;
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

        /* Sidebar tweaks */
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

# =============================
# Secrets / Configuration
# =============================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
RESOURCE = os.getenv("D365_RESOURCE", "https://squadd365.crm8.dynamics.com")

CONTACTS_API = f"{RESOURCE}/api/data/v9.2/contacts?$select=fullname,emailaddress1,telephone1,address1_city"
QUERYLOG_API = f"{RESOURCE}/api/data/v9.2/new_querylogs"

# OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# =============================
# Access Token (with caching)
# =============================
@st.cache_resource(ttl=3300, show_spinner=False)
def get_access_token():
    if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET, RESOURCE]):
        raise RuntimeError("Missing one or more Azure AD / D365 settings in environment variables.")
    auth_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": f"{RESOURCE}/.default",
        "grant_type": "client_credentials"
    }
    r = requests.post(auth_url, data=data)
    r.raise_for_status()
    return r.json()["access_token"]

# =============================
# Data: Fetch Contacts
# =============================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_contacts_from_d365():
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Accept": "application/json"
    }
    r = requests.get(CONTACTS_API, headers=headers)
    r.raise_for_status()
    data = r.json().get("value", [])
    df = pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame(columns=["FullName", "Email", "Phone", "City"])
    df = df.rename(columns={
        "fullname": "FullName",
        "emailaddress1": "Email",
        "telephone1": "Phone",
        "address1_city": "City"
    })
    cols = [c for c in ["FullName", "Email", "Phone", "City"] if c in df.columns] + \
           [c for c in df.columns if c not in ["FullName", "Email", "Phone", "City"]]
    return df[cols]

# =============================
# D365: Create Query Log
# =============================
def create_query_log_in_d365(user_query, gpt_result):
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0"
    }
    payload = {
        "new_userquery": (user_query or "")[:100],
        "new_userquery2": user_query or "",
        "new_gptresult": gpt_result or ""
    }
    r = requests.post(QUERYLOG_API, headers=headers, json=payload)
    if r.status_code not in (200, 201, 204):
        raise Exception(f"Failed to insert query log: {r.text}")

# =============================
# GPT Query
# =============================
def query_gpt(user_query, df, chat_history):
    data_text = df.to_csv(index=False)
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful data assistant. Answer with clear explanations, insights, "
                "or summaries based strictly on the dataset provided. Do NOT return code or "
                "programming instructions. Plain text only."
            ),
        },
        *chat_history,
        {"role": "user", "content": f"Here is the dataset:\n{data_text}"},
        {"role": "user", "content": user_query},
    ]
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=800,
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ GPT API error: {str(e)}"

# =============================
# Session State
# =============================
if "df" not in st.session_state:
    st.session_state.df = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "nav" not in st.session_state:
    st.session_state.nav = "Contacts"
# Auto-log is ON silently (no UI)
if "auto_log" not in st.session_state:
    st.session_state.auto_log = True

# =============================
# Sidebar (Left Pane): Title only
# =============================
with st.sidebar:
    st.markdown("## Dedupe assistant")
    st.markdown(
        '<div class="crm-card crm-subtle">Ask questions, find duplicates, and review contacts.</div>',
        unsafe_allow_html=True
    )
    # No environment details; no auto-log toggle

# =============================
# Top Command Row (Push Buttons + Actions)
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

# Handle navigation clicks OUTSIDE callbacks (so rerun works)
nav_changed = False
if click_contacts and st.session_state.nav != "Contacts":
    st.session_state.nav = "Contacts"
    nav_changed = True
elif click_assistant and st.session_state.nav != "Assistant":
    st.session_state.nav = "Assistant"
    nav_changed = True
elif click_logs and st.session_state.nav != "Logs":
    st.session_state.nav = "Logs"
    nav_changed = True

# Trigger a rerun (outside a callback) to immediately reflect active styles
if nav_changed:
    st.rerun()

# Right-side contextual action (top of area)
fetch_clicked = False
clear_clicked = False
with nav_cols[3]:
    if st.session_state.nav == "Contacts":
        fetch_clicked = st.button("📥 Fetch / Refresh Contacts", key="fetch_top", width="stretch")
    elif st.session_state.nav == "Logs":
        clear_clicked = st.button("🧹 Clear Local Conversation", key="clear_top", width="stretch")
    else:
        st.empty()

st.markdown('</div>', unsafe_allow_html=True)

# =============================
# Views
# =============================

# --- Contacts View ---
if st.session_state.nav == "Contacts":
    if fetch_clicked:
        with st.spinner("Fetching contacts from D365..."):
            try:
                st.session_state.df = fetch_contacts_from_d365()
                st.success(f"Fetched {len(st.session_state.df)} contacts from D365.")
            except Exception as e:
                st.error(f"❌ Error fetching contacts: {str(e)}")

    st.markdown("## Contacts")

    # Filters (above the grid)
    with st.expander("🔎 Filters", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            name_kw = st.text_input("Name contains", "")
        with col2:
            city_kw = st.text_input("City contains", "")
        with col3:
            email_kw = st.text_input("Email contains", "")

    if st.session_state.df is not None:
        df_view = st.session_state.df.copy()
        if 'name_kw' in locals() and name_kw:
            df_view = df_view[df_view["FullName"].fillna("").str.contains(name_kw, case=False, na=False)]
        if 'city_kw' in locals() and city_kw:
            df_view = df_view[df_view["City"].fillna("").str.contains(city_kw, case=False, na=False)]
        if 'email_kw' in locals() and email_kw:
            df_view = df_view[df_view["Email"].fillna("").str.contains(email_kw, case=False, na=False)]

        st.dataframe(df_view, width="stretch", height=420)
    else:
        st.info("Click **📥 Fetch / Refresh Contacts** above to load data from Dynamics 365.")

# --- Assistant View ---
elif st.session_state.nav == "Assistant":
    st.markdown("## Assistant")

    if st.session_state.df is None or st.session_state.df.empty:
        st.warning("No contacts loaded yet. Go to **Contacts** and click **📥 Fetch / Refresh Contacts**.")
    else:
        # Render chat history
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        # Chat input
        user_query = st.chat_input("Ask about the contacts (e.g., 'Top cities by contact count', 'How many contacts have email?')")
        if user_query:
            with st.chat_message("user"):
                st.write(user_query)
            with st.chat_message("assistant"):
                with st.spinner("Analyzing dataset..."):
                    result = query_gpt(user_query, st.session_state.df, st.session_state.chat_history)
                    st.write(result)

            st.session_state.chat_history.append({"role": "user", "content": user_query})
            st.session_state.chat_history.append({"role": "assistant", "content": result})

            # Silent auto-log to D365
            if st.session_state.auto_log:
                try:
                    create_query_log_in_d365(user_query, result)
                except Exception as e:
                    st.error(f"❌ Failed to log to D365: {str(e)}")

    # Helpful hints
    st.markdown(
        """
        <div class="crm-card">
          <div style="font-weight:600; margin-bottom:6px;">Try these</div>
          <div class="crm-subtle">
            • "Summarize contacts by city"<br/>
            • "List contacts with missing emails"<br/>
            • "Show Fuzzy duplicate contacts"
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# --- Logs View ---
elif st.session_state.nav == "Logs":
    if clear_clicked:
        st.session_state.chat_history = []
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
