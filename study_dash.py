import streamlit as st
from supabase import create_client, Client

# Initialize Streamlit Page
st.set_page_config(page_title="Study Logs Viewer", page_icon="📚", layout="centered")

st.title("📚 Study Logs & Notes")

# Initialize Supabase Client using Streamlit Secrets
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_ANON_KEY"]
supabase: Client = create_client(url, key)

# Fetch logs from the database
try:
    response = supabase.table("logs").select("*").execute()
    logs = response.data
except Exception as e:
    st.error(f"Failed to fetch data from Supabase: {e}")
    logs = []

if not logs:
    st.warning("No logs found in your database.")
else:
    for log in logs:
        subject = log.get("subject", "Untitled Subject")
        timestamp = log.get("timestamp", "Recent")
        exam_type = log.get("test_exam", "")
        notes = log.get("notes", "No markdown content provided.")
        
        # Create an expandable card for each log entry
        header_text = f"**{subject}** ({timestamp})"
        if exam_type:
            header_text += f" — *{exam_type}*"
            
        with st.expander(header_text):
            # Render the database content as Markdown
            st.markdown(notes)
