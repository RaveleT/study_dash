import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title="Study Logs App", page_icon="📚", layout="centered")

# Initialize Supabase Client
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_ANON_KEY"]
supabase: Client = create_client(url, key)

# Initialize authentication state
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# PIN Login Screen
if not st.session_state["authenticated"]:
    st.title("🔒 Enter PIN to Access")
    
    with st.form("pin_form"):
        entered_pin = st.text_input("PIN", type="password", max_chars=6)
        submit_button = st.form_submit_button("Unlock")
        
        if submit_button:
            # Compare with the PIN stored in your secrets.toml
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

    st.title("📚 Study Logs & Markdown Manager")

    tab1, tab2 = st.tabs(["View Logs", "Upload Markdown"])

    with tab1:
        st.header("Saved Study Notes")
        try:
            response = supabase.table("logs").select("*").execute()
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
                exam_type = log.get("test_exam", "")
                notes = log.get("notes", "No markdown content provided.")
                
                header_text = f"**{subject}** ({timestamp})"
                if exam_type:
                    header_text += f" — *{exam_type}*"
                    
                with st.expander(header_text):
                    st.markdown(notes)

    with tab2:
        st.header("Upload Markdown File")
        uploaded_file = st.file_uploader("Choose a Markdown file", type=["md", "txt"])
        subject_input = st.text_input("Subject Name", "General Notes")
        
        if uploaded_file is not None and st.button("Upload to Database"):
            markdown_content = uploaded_file.read().decode("utf-8")
            try:
                data = {
                    "subject": subject_input,
                    "notes": markdown_content,
                    "focus_state": "File Upload"
                }
                supabase.table("logs").insert(data).execute()
                st.success("Successfully uploaded markdown content to Supabase!")
            except Exception as e:
                st.error(f"Upload failed: {e}")
