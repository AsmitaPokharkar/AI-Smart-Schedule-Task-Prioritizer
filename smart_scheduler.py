import streamlit as st
import sqlite3
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

# ------------------------------
# Gemini SDK
try:
    from google import genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    st.warning("⚠️ google-genai not installed. Run: pip install google-genai")

# ------------------------------
# Configuration
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "your-api-key-here")

# ------------------------------
# Database Setup (using st.cache_resource to reuse connection)
@st.cache_resource
def get_db_connection():
    conn = sqlite3.connect("scheduler.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        deadline TEXT,
        hours REAL,
        priority_hint TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productivity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        log_date TEXT,
        hour_of_day INTEGER,
        focus_rating INTEGER,
        tasks_completed INTEGER DEFAULT 0
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_preferences (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    cursor.execute("INSERT OR IGNORE INTO user_preferences VALUES ('preferred_hours', '9-12,14-17,19-22')")
    cursor.execute("INSERT OR IGNORE INTO user_preferences VALUES ('max_hours_per_day', '6')")
    conn.commit()
    return conn, cursor

conn, cursor = get_db_connection()

# ------------------------------
# Helper functions (same as your original, slightly adapted)
def parse_task_with_llm(user_input: str) -> Optional[Dict]:
    if not HAS_GEMINI or GEMINI_API_KEY == "your-api-key-here":
        return parse_task_with_regex(user_input)
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""
    Extract task details from this sentence. Return ONLY valid JSON with fields: title, deadline (ISO format if date given, else null), hours (float), priority (low/medium/high). If no deadline, set null. If no hours, estimate reasonably.
    Input: {user_input}
    """
    try:
        response = client.models.generate_content(model='gemini-1.5-flash', contents=prompt)
        text = response.text.strip()
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```', '', text)
        return json.loads(text)
    except Exception as e:
        st.error(f"LLM error: {e}")
        return parse_task_with_regex(user_input)

def parse_task_with_regex(user_input: str) -> Dict:
    hours_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:hour|hr)s?', user_input, re.I)
    hours = float(hours_match.group(1)) if hours_match else 1.0
    priority = "medium"
    if re.search(r'\b(high|urgent|asap|important)\b', user_input, re.I):
        priority = "high"
    elif re.search(r'\b(low|optional|maybe)\b', user_input, re.I):
        priority = "low"
    deadline = None
    today = datetime.now().date()
    if "tomorrow" in user_input.lower():
        deadline = (today + timedelta(days=1)).isoformat()
    elif "friday" in user_input.lower():
        days_ahead = (4 - today.weekday()) % 7
        deadline = (today + timedelta(days=days_ahead)).isoformat()
    title = user_input[:50]
    return {"title": title, "deadline": deadline, "hours": hours, "priority": priority}

def compute_priority_score(task: Dict, proc_risk: float = 0.0) -> float:
    now = datetime.now()
    deadline = datetime.fromisoformat(task["deadline"]) if task.get("deadline") else None
    if deadline and deadline > now:
        days_left = (deadline - now).total_seconds() / 86400.0
        urgency = 1.0 / (days_left + 0.5)
    else:
        urgency = 2.0 if deadline and deadline <= now else 0.5
    effort = min(1.0, task["hours"] / 8.0)
    hint_map = {"low": 0.2, "medium": 0.6, "high": 1.0}
    hint = hint_map.get(task.get("priority_hint", "medium"), 0.6)
    risk = min(0.5, proc_risk * 0.1)
    return (0.5 * urgency) + (0.2 * effort) + (0.3 * hint) + risk

def get_best_hours() -> List[Tuple[int, int]]:
    cursor.execute("SELECT hour_of_day, AVG(focus_rating) FROM productivity_logs GROUP BY hour_of_day")
    rows = cursor.fetchall()
    if not rows:
        pref = cursor.execute("SELECT value FROM user_preferences WHERE key='preferred_hours'").fetchone()[0]
        blocks = pref.split(',')
        return [(int(b.split('-')[0]), int(b.split('-')[1])) for b in blocks]
    best = [row[0] for row in rows if row[1] and row[1] > 3.5]
    if not best:
        return [(9, 12), (14, 17)]
    best.sort()
    blocks = []
    start = best[0]
    end = start
    for h in best[1:]:
        if h == end + 1:
            end = h
        else:
            blocks.append((start, end+1))
            start = h
            end = h
    blocks.append((start, end+1))
    return blocks

def get_free_blocks(date: datetime.date) -> List[Tuple[datetime, datetime]]:
    best_hours = get_best_hours()
    free_blocks = []
    for start_hour, end_hour in best_hours:
        start = datetime(date.year, date.month, date.day, start_hour, 0)
        end = datetime(date.year, date.month, date.day, end_hour, 0)
        free_blocks.append((start, end))
    return free_blocks

def schedule_tasks(tasks: List[Dict], days_ahead: int = 7) -> List[Dict]:
    for t in tasks:
        t["priority_score"] = compute_priority_score(t, 0.0)
    tasks_sorted = sorted(tasks, key=lambda x: x["priority_score"], reverse=True)
    schedule = []
    today = datetime.now().date()
    for day_offset in range(days_ahead):
        date = today + timedelta(days=day_offset)
        free_blocks = get_free_blocks(date)
        remaining_tasks = []
        for task in tasks_sorted:
            if task["status"] != "pending":
                continue
            assigned = False
            for i, (blk_start, blk_end) in enumerate(free_blocks):
                duration = timedelta(hours=task["hours"])
                if blk_end - blk_start >= duration:
                    start = blk_start
                    end = start + duration
                    schedule.append({
                        "task_id": task["id"],
                        "title": task["title"],
                        "start": start.isoformat(),
                        "end": end.isoformat()
                    })
                    if end < blk_end:
                        free_blocks[i] = (end, blk_end)
                    else:
                        free_blocks.pop(i)
                    assigned = True
                    break
            if not assigned:
                remaining_tasks.append(task)
        tasks_sorted = remaining_tasks
        if not tasks_sorted:
            break
    return schedule

def explain_schedule(schedule: List[Dict]) -> str:
    if not HAS_GEMINI or GEMINI_API_KEY == "your-api-key-here":
        return "AI explanation not available (missing Gemini API key)."
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""
    You are a friendly study coach. Here is the user's schedule for today and upcoming days:
    {json.dumps(schedule, indent=2)}
    Write a short, motivational explanation (2-3 sentences) about why the hardest tasks are placed in certain time slots, and how this helps the student.
    """
    try:
        response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return response.text.strip()
    except Exception as e:
        return f"I've built your schedule based on deadlines and your focus patterns. (Error: {e})"

def add_task_from_input(user_input: str):
    parsed = parse_task_with_llm(user_input)
    if not parsed:
        return False, "Could not parse task."
    now_str = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO tasks (title, deadline, hours, priority_hint, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (parsed.get("title", "Untitled"), parsed.get("deadline"),
          parsed.get("hours", 1.0), parsed.get("priority", "medium"),
          "pending", now_str))
    conn.commit()
    return True, f"✅ Task added: {parsed['title']}"

def log_feedback(task_title: str, focus_rating: int, completed: bool = True):
    hour = datetime.now().hour
    today_str = datetime.now().date().isoformat()
    cursor.execute("""
        INSERT INTO productivity_logs (log_date, hour_of_day, focus_rating, tasks_completed)
        VALUES (?, ?, ?, ?)
    """, (today_str, hour, focus_rating, 1 if completed else 0))
    conn.commit()
    if completed:
        cursor.execute("UPDATE tasks SET status='done' WHERE title=?", (task_title,))
        conn.commit()
    return f"⭐ Thanks for your feedback on '{task_title}'!"

# ------------------------------
# Streamlit UI
st.set_page_config(page_title="AI Smart Scheduler", layout="wide")
st.title("🧠 AI Smart Schedule & Task Prioritizer")
st.markdown("Manage your tasks, get AI‑powered schedules, and improve your productivity.")

# Sidebar for adding tasks
with st.sidebar:
    st.header("➕ Add New Task")
    task_input = st.text_area("Describe your task (e.g., 'Math homework due Friday, 2 hours, high priority')")
    if st.button("Add Task"):
        if task_input:
            success, msg = add_task_from_input(task_input)
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
        else:
            st.warning("Please enter a task description.")

# Main area tabs
tab1, tab2, tab3 = st.tabs(["📅 Schedule", "📝 Feedback", "📊 Productivity"])

with tab1:
    st.subheader("Your Upcoming Schedule")
    cursor.execute("SELECT id, title, deadline, hours, priority_hint, status FROM tasks WHERE status='pending'")
    tasks = [{"id": row[0], "title": row[1], "deadline": row[2], "hours": row[3], "priority_hint": row[4], "status": row[5]} for row in cursor.fetchall()]
    if not tasks:
        st.info("No pending tasks. Add one from the sidebar!")
    else:
        schedule = schedule_tasks(tasks, days_ahead=3)
        if schedule:
            import pandas as pd
            df = []
            for item in schedule:
                start = datetime.fromisoformat(item["start"])
                df.append({
                    "Day": start.strftime("%a %b %d"),
                    "Time": start.strftime("%H:%M"),
                    "Task": item["title"],
                    "Duration (h)": round((datetime.fromisoformat(item["end"]) - start).total_seconds()/3600, 1)
                })
            st.dataframe(pd.DataFrame(df), use_container_width=True)
            with st.expander("🧑‍🏫 AI Coach Explanation"):
                explanation = explain_schedule(schedule)
                st.write(explanation)
        else:
            st.warning("Could not generate schedule. Check your free time blocks or task deadlines.")

with tab2:
    st.subheader("Give Feedback on a Completed Task")
    cursor.execute("SELECT title FROM tasks WHERE status='pending'")
    pending_tasks = [row[0] for row in cursor.fetchall()]
    if pending_tasks:
        task_to_feedback = st.selectbox("Select a task you completed", pending_tasks)
        rating = st.slider("Focus rating (1 = very distracted, 5 = highly focused)", 1, 5, 4)
        completed_flag = st.checkbox("Mark as completed", value=True)
        if st.button("Submit Feedback"):
            msg = log_feedback(task_to_feedback, rating, completed_flag)
            st.success(msg)
            st.rerun()
    else:
        st.info("No pending tasks to give feedback on. Add a task first!")

with tab3:
    st.subheader("Your Productivity Insights")
    cursor.execute("SELECT log_date, hour_of_day, focus_rating FROM productivity_logs ORDER BY log_date DESC LIMIT 10")
    logs = cursor.fetchall()
    if logs:
        st.write("Recent feedback logs:")
        for log in logs:
            st.write(f"📅 {log[0]} at {log[1]}:00 → focus {log[2]}/5")
        best = get_best_hours()
        st.write(f"🧠 Your best focus hours (learned): {', '.join([f'{s}-{e}' for s,e in best])}")
    else:
        st.info("No feedback yet. Complete tasks and rate them to see insights.")

# Footer
st.markdown("---")
st.caption("Powered by Gemini AI | Schedule based on priority + focus learning")
