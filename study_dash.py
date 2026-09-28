from datetime import datetime, timedelta
import os
import signal
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
from supabase import Client, create_client

# ====================== CONFIG & SUPABASE ======================
st.set_page_config(page_title="Study Dash & Notes", page_icon="🔥", layout="wide")

# Initialize Supabase Client using your credentials format
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_ANON_KEY"]
supabase: Client = create_client(url, key)

# ====================== AUTHENTICATION STATE ======================
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# PIN Login Screen
if not st.session_state["authenticated"]:
    st.title("🔒 Enter PIN to Access Study Dashboard")
    
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
    # Main App (Post-Login)[cite: 1]
    if st.sidebar.button("🔒 Lock App"):
        st.session_state["authenticated"] = False
        st.rerun()

    # ====================== TIME & SESSION STATE ======================
    now = datetime.now()
    today = now.date()

    if "t_stop" not in st.session_state:
        st.session_state.t_stop = now.replace(hour=18, minute=0, second=0).time()
    if "t_start" not in st.session_state:
        st.session_state.t_start = now.replace(hour=8, minute=0, second=0).time()
    if "triggered_milestones" not in st.session_state:
        st.session_state.triggered_milestones = set()
    if "last_mode" not in st.session_state:
        st.session_state.last_mode = None
    if "subjects" not in st.session_state:
        st.session_state.subjects = [
            "MAT 2247: Numerical Analysis II",
            "STA 2242",
            "Physics",
            "Chemistry",
            "Computer Science",
            "General Notes"
        ]

    # Timing parameters
    sd = datetime.combine(today, st.session_state.t_start)
    ed = datetime.combine(today, st.session_state.t_stop)
    total_session_seconds = max(1.0, (ed - sd).total_seconds())

    if now >= ed:
        current_mode = "COMPLETE"
        pomodoro_rem = 0
        tab_percent = 100
    else:
        mins = now.minute
        current_mode = "FOCUS" if (0 <= mins < 25) or (30 <= mins < 55) else "BREAK"

        next_milestone_min = 25 if mins < 25 else (55 if current_mode == "FOCUS" else (30 if mins < 30 else 60))
        pomodoro_rem_dt = now.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=next_milestone_min)
        pomodoro_rem_mins = int((pomodoro_rem_dt - now).total_seconds() / 60)
        mins_to_session_end = int((ed - now).total_seconds() / 60)

        pomodoro_rem = max(0, min(pomodoro_rem_mins, mins_to_session_end))
        tab_percent = int(min(100, max(0, (now - sd).total_seconds() / total_session_seconds * 100)))

    # ====================== SUPABASE DATABASE FUNCTIONS ======================
    def save_log(subject, test_exam, focus_state, focus_score, duration_minutes, notes):
        supabase.table("logs").insert({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "subject": subject,
            "test_exam": test_exam,
            "focus_state": focus_state,
            "focus_score": focus_score,
            "duration_minutes": duration_minutes,
            "notes": notes
        }).execute()

    def load_logs():
        try:
            response = supabase.table("logs").select("*").order("id", desc=True).execute()
            if not response.data:
                return pd.DataFrame(columns=["timestamp", "subject", "test_exam", "focus_state", "focus_score", "duration_minutes", "notes"])
            df = pd.DataFrame(response.data)
            df = df.rename(columns={
                "timestamp": "Timestamp",
                "subject": "Subject",
                "test_exam": "Test_Exam",
                "focus_state": "Focus_State",
                "focus_score": "Focus_Score",
                "duration_minutes": "Duration_Minutes",
                "notes": "Notes"
            })
            return df
        except Exception:
            return pd.DataFrame(columns=["Timestamp", "Subject", "Test_Exam", "Focus_State", "Focus_Score", "Duration_Minutes", "Notes"])

    def add_assessment(task, course, effort_type, start_date, start_time, end_time, duration_mins):
        supabase.table("assessments").insert({
            "task": task,
            "course": course,
            "effort_type": effort_type,
            "start_date": str(start_date),
            "start_time": str(start_time),
            "end_time": str(end_time),
            "duration_mins": duration_mins
        }).execute()

    def load_assessments():
        try:
            response = supabase.table("assessments").select("*").order("start_date", desc=False).execute()
            if not response.data:
                return pd.DataFrame(columns=["id", "task", "course", "effort_type", "start_date", "start_time", "end_time", "duration_mins"])
            return pd.DataFrame(response.data)
        except Exception:
            return pd.DataFrame()

    def delete_assessment(assessment_id):
        supabase.table("assessments").delete().eq("id", assessment_id).execute()

    def add_timetable_class(course, day_of_week, start_time, end_time, location):
        supabase.table("timetable").insert({
            "course": course,
            "day_of_week": day_of_week,
            "start_time": str(start_time),
            "end_time": str(end_time),
            "location": location
        }).execute()

    def load_timetable():
        try:
            response = supabase.table("timetable").select("*").order("day_of_week", desc=False).order("start_time", desc=False).execute()
            if not response.data:
                return pd.DataFrame(columns=["id", "course", "day_of_week", "start_time", "end_time", "location"])
            return pd.DataFrame(response.data)
        except Exception:
            return pd.DataFrame()

    def delete_timetable_class(class_id):
        supabase.table("timetable").delete().eq("id", class_id).execute()

    # ====================== HELPERS ======================
    def get_next_class_datetime(current_dt, day_of_week, start_time_str):
        target_time = datetime.strptime(start_time_str, "%H:%M:%S").time() if len(start_time_str) == 8 else datetime.strptime(start_time_str, "%H:%M").time()
        days_ahead = day_of_week - current_dt.weekday()
        if days_ahead < 0:
            days_ahead += 7
        elif days_ahead == 0 and current_dt.time() >= target_time:
            days_ahead += 7
        return datetime.combine(current_dt.date() + timedelta(days=days_ahead), target_time)

    def format_time_remaining(time_delta):
        total_seconds = int(time_delta.total_seconds())
        days, hours, minutes = total_seconds // 86400, (total_seconds % 86400) // 3600, (total_seconds % 3600) // 60
        parts = []
        if days > 0: parts.append(f"{days}d")
        if hours > 0 or days > 0: parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        return " ".join(parts)

    def trigger_alert(message, is_milestone=False):
        st.toast(message, icon="🔔")
        delay_ms = 100 if is_milestone else 0
        components.html(f"""
        <script>
            setTimeout(function() {{
                var audio = new Audio('https://codeskulptor-demos.commondatastorage.googleapis.com/pang/arrow.mp3');
                audio.play().catch(e => console.log('Audio failed:', e));
            }}, {delay_ms});
        </script>
        """, height=0)

    # Mode transition audio triggers
    if st.session_state.last_mode is not None and st.session_state.last_mode != current_mode:
        if st.session_state.last_mode == "FOCUS" and current_mode == "BREAK":
            trigger_alert("Focus session ended! Time for a break ☕", is_milestone=True)
        elif st.session_state.last_mode == "BREAK" and current_mode == "FOCUS":
            trigger_alert("Break session ended! Time to focus 🔥", is_milestone=True)
        elif current_mode == "COMPLETE":
            trigger_alert("Daily session complete! Great work 🏆", is_milestone=True)
    st.session_state.last_mode = current_mode

    # ====================== NAVIGATION TABS ======================
    st.title("🔥 Study Dash & Notes Hub")
    st_autorefresh(interval=10000, key="datarefresh", limit=None, debounce=False)

    tab_dash, tab_assessments, tab_timetable, tab_notes = st.tabs([
        "⏱️ Daily Tracker", 
        "📝 Tests & Assessments", 
        "📅 Timetable & Countdowns", 
        "📚 Notes Library & Uploader"
    ])

    # ----------------------------------------------------
    # TAB 1: DAILY DASHBOARD
    # ----------------------------------------------------
    with tab_dash:
        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("⏱️ Session Status")
            color = "#00FF00" if current_mode == "FOCUS" else ("#00BCFF" if current_mode == "BREAK" else "#FFD700")
            label_suffix = " (Session Complete!)" if current_mode == "COMPLETE" else ""
            st.markdown(f"<h1 style='color: {color};'>{current_mode}{label_suffix}</h1>", unsafe_allow_html=True)

            elapsed_seconds = (now - sd).total_seconds()
            total_progress = max(0.0, min(1.0, elapsed_seconds / total_session_seconds))
            
            st.metric("🍅 Pomodoro Remaining", f"{pomodoro_rem} minutes")
            st.metric("📊 Global Progress", f"{tab_percent}%", delta=f"{int(elapsed_seconds/60)} of {int(total_session_seconds/60)} min")

            st.divider()
            st.progress(total_progress)
            st.write(f"**Daily Goal Progress: {tab_percent}%**")

            st.subheader("📊 Log Study Session")
            with st.form("study_form", clear_on_submit=True):
                subject = st.selectbox("Subject / Module", options=st.session_state.subjects)
                new_subject = st.text_input("Add new subject", placeholder="e.g. Quantum Mechanics")
                test_exam = st.text_input("Test / Exam (optional)", placeholder="Midterm, Quiz")

                focus_map = {
                    "Deep Flow (No distractions)": 10,
                    "Active Work (Steady)": 7,
                    "Manual Work/Writing": 8,
                    "Shallow/Admin (Easy)": 4,
                    "Distracted/Struggling": 2,
                }
                state = st.selectbox("Focus Level", list(focus_map.keys()), index=1)
                notes_input = st.text_area("Notes / Summary")
                duration_manual = st.number_input("Duration (minutes)", min_value=0, value=25, step=5)

                if st.form_submit_button("🔒 Log Session"):
                    final_subject = new_subject.strip() if new_subject.strip() else subject
                    if final_subject:
                        if final_subject not in st.session_state.subjects:
                            st.session_state.subjects.append(final_subject)
                        save_log(final_subject, test_exam.strip(), state, focus_map[state], duration_manual, notes_input.strip())
                        st.success(f"✅ Logged {duration_manual} mins for **{final_subject}**")
                        st.rerun()

        with col2:
            st.subheader("📅 Daily Timeline")
            t1, t2 = st.columns(2)
            with t1:
                t_start_input = st.time_input("Today's Start", value=st.session_state.t_start)
            with t2:
                t_stop_input = st.time_input("Planned Finish", value=st.session_state.t_stop)

            if t_start_input != st.session_state.t_start or t_stop_input != st.session_state.t_stop:
                st.session_state.t_start = t_start_input
                st.session_state.t_stop = t_stop_input
                st.rerun()

            fig_time = px.timeline(pd.DataFrame([dict(Task="Session", Start=sd, Finish=ed)]), x_start="Start", x_end="Finish", y="Task", color_discrete_sequence=["#00CC96"])
            fig_time.add_vline(x=now, line_width=3, line_dash="dash", line_color="red")
            fig_time.update_layout(height=120, showlegend=False, margin=dict(l=0, r=0, t=0, b=0), yaxis={"visible": False})
            st.plotly_chart(fig_time, use_container_width=True)

            st.divider()
            st.subheader("📈 Focus Trends & Time per Subject")
            history = load_logs()

            if not history.empty and "Timestamp" in history.columns:
                history["Timestamp"] = pd.to_datetime(history["Timestamp"], errors='coerce')
                history_sorted = history.dropna(subset=["Timestamp"]).sort_values("Timestamp")
                if not history_sorted.empty:
                    history_sorted["Smooth_Score"] = history_sorted["Focus_Score"].ewm(span=3, adjust=False).mean()

                    fig_trend = go.Figure()
                    fig_trend.add_trace(go.Scatter(x=history_sorted["Timestamp"], y=history_sorted["Smooth_Score"], mode="lines+markers", line=dict(shape="spline", smoothing=1.3, width=4, color="#00FF00")))
                    fig_trend.update_layout(template="plotly_dark", height=280, yaxis=dict(range=[0, 11]))
                    st.plotly_chart(fig_trend, use_container_width=True)

                if "Subject" in history.columns and "Duration_Minutes" in history.columns:
                    time_per_subject = history.groupby("Subject")["Duration_Minutes"].sum().reset_index()
                    fig_bar = px.bar(time_per_subject, x="Subject", y="Duration_Minutes", title="Time Studied per Subject")
                    st.plotly_chart(fig_bar, use_container_width=True)

    # ----------------------------------------------------
    # TAB 2: TESTS & ASSESSMENTS
    # ----------------------------------------------------
    with tab_assessments:
        st.header("📝 Assessment & Exam Schedule")

        with st.expander("➕ Add New Test / Quiz / Exam", expanded=False):
            with st.form("assessment_form", clear_on_submit=True):
                f1, f2, f3 = st.columns(3)
                with f1:
                    task_name = st.text_input("Task Name", placeholder="e.g. MAT 2247 Test 1")
                    course_name = st.selectbox("Course", options=st.session_state.subjects)
                with f2:
                    effort = st.selectbox("Effort Type", ["Test", "Quiz", "Exam", "Assignment", "Lab"])
                    assessment_date = st.date_input("Date", value=today + timedelta(days=7))
                with f3:
                    start_time = st.time_input("Start Time", value=datetime.strptime("08:00", "%H:%M").time())
                    end_time = st.time_input("End Time", value=datetime.strptime("09:00", "%H:%M").time())

                dur = max(0, int((datetime.combine(today, end_time) - datetime.combine(today, start_time)).total_seconds() / 60))

                if st.form_submit_button("📌 Save Assessment"):
                    if task_name:
                        add_assessment(task_name, course_name, effort, assessment_date, start_time, end_time, dur)
                        st.success(f"Assessment '{task_name}' added successfully!")
                        st.rerun()
                    else:
                        st.error("Please enter a Task Name.")

        df_assess = load_assessments()

        if not df_assess.empty and "start_date" in df_assess.columns:
            df_assess["Date_Obj"] = pd.to_datetime(df_assess["start_date"]).dt.date
            df_assess["Days_Left"] = (df_assess["Date_Obj"] - today).apply(lambda x: x.days)

            m1, m2, m3 = st.columns(3)
            upcoming_count = len(df_assess[df_assess["Days_Left"] >= 0])
            next_due = df_assess[df_assess["Days_Left"] >= 0]["Days_Left"].min() if upcoming_count > 0 else "N/A"

            m1.metric("Total Scheduled", len(df_assess))
            m2.metric("Upcoming Assessments", upcoming_count)
            m3.metric("Next Assessment In", f"{next_due} Days" if pd.notna(next_due) else "N/A")

            st.subheader("📋 Assessment List")
            for idx, row in df_assess.iterrows():
                with st.container():
                    c1, c2, c3, c4, c5 = st.columns([3, 2, 3, 2, 1])
                    badge_color = "#4A4A4A" if row["Days_Left"] < 0 else ("#D32F2F" if row["Days_Left"] <= 7 else "#2E7D32")
                    c1.markdown(f"**📝 {row['task']}**")
                    c2.markdown(f"<span style='background-color: {badge_color}; padding: 3px 8px; border-radius: 5px; color: white;'>⏳ {row['Days_Left']} days</span>", unsafe_allow_html=True)
                    c3.markdown(f"📅 {row['start_date']} ({row['start_time'][:5]} → {row['end_time'][:5]})")
                    c4.markdown(f"**{row['effort_type']}** | {row['course']}")
                    if c5.button("🗑️", key=id := f"del_assess_{row.get('id', idx)}"):
                        delete_assessment(row["id"])
                        st.rerun()
                st.divider()
        else:
            st.info("No assessments or exams added yet.")

    # ----------------------------------------------------
    # TAB 3: TIMETABLE & COUNTDOWNS
    # ----------------------------------------------------
    with tab_timetable:
        st.header("📅 Weekly Timetable & Class Countdown")
        days_map = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}

        with st.expander("➕ Add Class to Weekly Timetable", expanded=False):
            with st.form("timetable_form", clear_on_submit=True):
                tc1, tc2, tc3 = st.columns(3)
                with tc1:
                    t_course = st.selectbox("Course", options=st.session_state.subjects)
                    t_day = st.selectbox("Day of Week", list(days_map.values()))
                with tc2:
                    t_start = st.time_input("Start Time", value=datetime.strptime("09:00", "%H:%M").time())
                    t_end = st.time_input("End Time", value=datetime.strptime("11:00", "%H:%M").time())
                with tc3:
                    t_location = st.text_input("Venue / Link", placeholder="Room 402 or Online")

                if st.form_submit_button("📌 Add Class"):
                    day_num = [k for k, v in days_map.items() if v == t_day][0]
                    add_timetable_class(t_course, day_num, t_start, t_end, t_location)
                    st.success(f"Added {t_course} on {t_day}s!")
                    st.rerun()

        df_tt = load_timetable()
        if not df_tt.empty:
            for idx, row in df_tt.iterrows():
                day_num = row["day_of_week"]
                s_time_str = row["start_time"][:5]
                e_time_str = row["end_time"][:5]
                class_start_dt = get_next_class_datetime(now, day_num, row["start_time"])
                class_end_dt = datetime.combine(class_start_dt.date(), datetime.strptime(e_time_str, "%H:%M").time())

                is_today = (now.weekday() == day_num)
                if is_today and s_time_str <= now.strftime("%H:%M") <= e_time_str:
                    cd_text, badge_color = f"🟢 IN PROGRESS ({int((class_end_dt - now).total_seconds()/60)}m left)", "#2E7D32"
                else:
                    time_until = class_start_dt - now
                    cd_text, badge_color = f"⏳ in {format_time_remaining(time_until)}", ("#D32F2F" if time_until.total_seconds() <= 7200 else "#1E88E5")

                c1, c2, c3, c4 = st.columns([2.5, 2.5, 3, 0.5])
                c1.markdown(f"**📚 {row['course']}**")
                c2.markdown(f"<span style='background-color: {badge_color}; padding: 4px 10px; border-radius: 6px; color: white; font-weight: bold;'>{cd_text}</span>", unsafe_allow_html=True)
                c3.markdown(f"🗓️ **{days_map[row['day_of_week']]}s** | {s_time_str} → {e_time_str} | 📍 {row.get('location', '')}")
                if c4.button("🗑️", key=f"del_tt_{row['id']}"):
                    delete_timetable_class(row["id"])
                    st.rerun()
                st.divider()
        else:
            st.info("No recurring weekly classes scheduled.")

    # ----------------------------------------------------
    # TAB 4: NOTES LIBRARY & UPLOADER (Supports Markdown & HTML)
    # ----------------------------------------------------
    with tab_notes:
        st.header("📚 Saved Lecture Notes & File Library")
        
        sub_filter = st.selectbox("Filter by Subject", ["All"] + st.session_state.subjects)
        logs_df = load_logs()

        if not logs_df.empty:
            if sub_filter != "All":
                filtered_logs = logs_df[logs_df["Subject"] == sub_filter]
            else:
                filtered_logs = logs_df

            if filtered_logs.empty:
                st.warning("No notes found for this filter.")
            else:
                for _, log in filtered_logs.iterrows():
                    subj = log.get("Subject", "Untitled")
                    ts = log.get("Timestamp", "Recent")
                    f_state = log.get("Focus_State", "Standard")
                    notes_content = log.get("Notes", "No content provided.")

                    header_text = f"**{subj}** ({ts}) — *{f_state}*"
                    with st.expander(header_text):
                        # Smart check to auto-render HTML vs Markdown[cite: 1]
                        stripped = notes_content.strip().lower()
                        if stripped.startswith("<!doctype") or stripped.startswith("<html") or stripped.startswith("<div"):
                            components.html(notes_content, height=500, scrolling=True)
                        else:
                            st.markdown(notes_content)
        else:
            st.warning("No notes stored in Supabase yet.")

        st.divider()
        st.subheader("📤 Upload Chapter File (Markdown or HTML)")
        
        with st.form("upload_form", clear_on_submit=True):
            uploaded_file = st.file_uploader("Choose file", type=["md", "txt", "html"])
            subject_input = st.selectbox("Assign to Subject", options=st.session_state.subjects)
            category_input = st.selectbox("Category", ["Chapter Notes", "Lecture Example", "Algorithm Reference", "HTML Render", "File Upload"])
            
            if st.form_submit_button("Upload to Supabase Database"):
                if uploaded_file is not None:
                    file_text = uploaded_file.read().decode("utf-8")
                    try:
                        save_log(
                            subject=subject_input,
                            test_exam="",
                            focus_state=category_input,
                            focus_score=8,
                            duration_minutes=0,
                            notes=file_text
                        )
                        st.success(f"Successfully uploaded {uploaded_file.name} to Supabase!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Upload failed: {e}")
                else:
                    st.warning("Please select a file to upload.")

    # ====================== SIDEBAR ======================
    st.sidebar.subheader("⚙️ System Control")
    if st.sidebar.button("🚨 STOP APP PROCESS"):
        os.kill(os.getpid(), signal.SIGTERM)
    if st.sidebar.button("🎵 Test Chime"):
        trigger_alert("Audio test successful!")

    st.sidebar.divider()
    st.sidebar.subheader("📌 Session Summary")
    st.sidebar.write(f"**Start Time:** {st.session_state.t_start.strftime('%I:%M %p')}")
    st.sidebar.write(f"**End Time:** {st.session_state.t_stop.strftime('%I:%M %p')}")
    st.sidebar.write(f"**Progress:** {tab_percent}%")
    st.sidebar.write(f"**Pomodoro Left:** {pomodoro_rem}m")

    history_sidebar = load_logs()
    total_today = 0
    if not history_sidebar.empty and "Timestamp" in history_sidebar.columns:
        history_sidebar["Timestamp"] = pd.to_datetime(history_sidebar["Timestamp"], errors='coerce')
        today_logs = history_sidebar[history_sidebar["Timestamp"].dt.date == today]
        total_today = int(today_logs["Duration_Minutes"].sum()) if not today_logs.empty else 0

    st.sidebar.metric("⏱️ Total Studied Today", f"{total_today} minutes")
    st.sidebar.caption(f"🔄 Auto-refresh: 10s | Mode: {current_mode}")
