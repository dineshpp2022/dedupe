import streamlit as st
import pandas as pd
import requests
import os
from openai import OpenAI

# -----------------------------
# Load secrets from environment variables
# -----------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
RESOURCE = os.getenv("D365_RESOURCE", "https://squadd365.crm8.dynamics.com")  # default if not set

# -----------------------------
# OpenAI client
# -----------------------------
client = OpenAI(api_key=OPENAI_API_KEY)

CONTACTS_API = f"{RESOURCE}/api/data/v9.2/contacts?$select=fullname,emailaddress1,telephone1,address1_city"
QUERYLOG_API = f"{RESOURCE}/api/data/v9.2/new_querylogs"

# -----------------------------
# Get Access Token
# -----------------------------
def get_access_token():
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

# -----------------------------
# Fetch contacts from D365 CRM
# -----------------------------
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
    data = r.json()["value"]
    df = pd.DataFrame(data)
    df = df.rename(columns={
        "fullname": "FullName",
        "emailaddress1": "Email",
        "telephone1": "Phone",
        "address1_city": "City"
    })
    return df

# -----------------------------
# Store GPT Query into D365 CRM
# -----------------------------
def create_query_log_in_d365(user_query, gpt_result):
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0"
    }
    payload = {
        "new_userquery": user_query[:100],
        "new_userquery2": user_query,
        "new_gptresult": gpt_result
    }
    r = requests.post(QUERYLOG_API, headers=headers, json=payload)
    if r.status_code not in (200, 204, 201):
        raise Exception(f"Failed to insert query log: {r.text}")

# -----------------------------
# Query GPT
# -----------------------------
def query_gpt(user_query, df, chat_history):
    data_text = df.to_csv(index=False)
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful data assistant. "
                "Answer only with clear explanations, insights, or summaries "
                "based on the dataset provided. "
                "Do NOT return Python/SQL/dot net programming instructions. "
                "Plain text only."
            ),
        }
    ]
    messages += chat_history
    messages.append({"role": "user", "content": f"Here is the dataset:\n{data_text}"})
    messages.append({"role": "user", "content": user_query})

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=800
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ GPT API error: {str(e)}"

# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="D365 Contact Assistant", page_icon="📊")
st.title("📊 D365 Contact Dataset Query Assistant")

if "df" not in st.session_state:
    st.session_state.df = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if st.button("Fetch Contacts from D365 CRM"):
    try:
        df = fetch_contacts_from_d365()
        st.session_state.df = df
        st.success(f"✅ Fetched {len(df)} contacts from D365 CRM.")
        st.dataframe(df.head())
    except Exception as e:
        st.error(f"❌ Error fetching contacts: {str(e)}")

if st.session_state.df is not None:
    user_query = st.text_input("Ask a question about the dataset:")

    if st.button("Ask GPT") and user_query:
        result = query_gpt(user_query, st.session_state.df, st.session_state.chat_history)
        st.markdown("### GPT Result")
        st.write(result)

        try:
            create_query_log_in_d365(user_query, result)
            st.success("✅ Query logged into D365 CRM.")
        except Exception as e:
            st.error(f"❌ Failed to log query: {str(e)}")

        st.session_state.chat_history.append({"role": "user", "content": user_query})
        st.session_state.chat_history.append({"role": "assistant", "content": result})

        with st.expander("Conversation History"):
            for msg in st.session_state.chat_history:
                st.markdown(f"**{msg['role']}**: {msg['content']}")

