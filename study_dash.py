from datetime import datetime
import streamlit as st
from supabase import Client, create_client

st.set_page_config(page_title="MAT 2247 Study Logs", page_icon="📚", layout="centered")

# Initialize Supabase Client
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_ANON_KEY"]
supabase: Client = create_client(url, key)

# Initialize authentication state
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# PIN Login Screen
if not st.session_state["authenticated"]:
    st.title("🔒 Enter PIN to Access Notes")
    
    with st.form("pin_form"):
        entered_pin = st.text_input("PIN", type="password", max_chars=6)
        submit_button = st.form_submit_button("Unlock")
        
        if submit_button:
            if entered_pin == st.secrets["APP_PIN"]:
                st.session_state["authenticated"] = True
                st.success("Access granted!")
                st.rerun()
            else:
                st.error("Incorrect PIN. Try again.")

else:
    # Main App (Post-Login)
    if st.sidebar.button("Lock App"):
        st.session_state["authenticated"] = False
        st.rerun()

    st.title("📚 MAT 2247: Numerical Analysis II Notes")

    tab1, tab2 = st.tabs(["View Study Logs", "Upload Markdown Notes"])

    with tab1:
        st.header("Saved Lecture & Chapter Notes")
        
        # Subject filter option
        selected_subject = st.selectbox("Filter by Subject", ["All", "MAT 2247: Numerical Analysis II", "General Notes"])
        
        try:
            query = supabase.table("logs").select("*").order("id", desc=True)
            if selected_subject != "All":
                query = query.eq("subject", selected_subject)
            response = query.execute()
            logs = response.data
        except Exception as e:
            st.error(f"Failed to fetch data: {e}")
            logs = []

        if not logs:
            st.warning("No logs found in your database.")
        else:
            for log in logs:
                subject = log.get("subject", "Untitled Subject")
                timestamp = log.get("timestamp", "Recent")
                focus_state = log.get("focus_state", "Standard")
                notes = log.get("notes", "No markdown content provided.")
                
                header_text = f"**{subject}** ({timestamp}) — *{focus_state}*"
                    
                with st.expander(header_text):
                    st.markdown(notes)

    with tab2:
        st.header("Upload Chapter Markdown")
        uploaded_file = st.file_uploader("Choose a Markdown file (.md)", type=["md", "txt"])
        subject_input = st.text_input("Subject Name", "MAT 2247: Numerical Analysis II")
        focus_input = st.selectbox("Category", ["Chapter Notes", "Lecture Example", "Algorithm Reference", "File Upload"])
        
        if uploaded_file is not None and st.button("Upload to Database"):
            markdown_content = uploaded_file.read().decode("utf-8")
            try:
                data = {
                    "subject": subject_input,
                    "notes": markdown_content,
                    "focus_state": focus_input,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                supabase.table("logs").insert(data).execute()
                st.success("Successfully uploaded markdown content to Supabase!")
            except Exception as e:
                st.error(f"Upload failed: {e}")
