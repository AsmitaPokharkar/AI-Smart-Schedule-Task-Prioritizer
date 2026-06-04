import sqlite3
import json
import datetime
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import re
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ------------------------------
# Gemini SDK 
try:
    from google import genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    print(" !!!!  google-genai not installed. Run: pip install google-genai !!!!!!!")

# Configuration
GEMINI_API_KEY = "api key here "

# ------------------------------
# Database Setup

conn = sqlite3.connect("scheduler.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    deadline TEXT,          -- ISO format
    hours REAL,
    priority_hint TEXT,     -- low, medium, high
    status TEXT DEFAULT 'pending', -- pending, done, delayed
    created_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS productivity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date TEXT,
    hour_of_day INTEGER,
    focus_rating INTEGER,   -- 1 to 5
    tasks_completed INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_preferences (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")
conn.commit()

# Default
cursor.execute("INSERT OR IGNORE INTO user_preferences VALUES ('preferred_hours', '9-12,14-17,19-22')")
cursor.execute("INSERT OR IGNORE INTO user_preferences VALUES ('max_hours_per_day', '6')")
conn.commit()

# ------------------------------
# LLM Parser (Gemini or Fallback logic )

def parse_task_with_llm(user_input: str) -> Optional[Dict]:
    if not HAS_GEMINI:
        return parse_task_with_regex(user_input)
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""
    Extract task details from this sentence. Return ONLY valid JSON with fields: title, deadline (ISO format if date given, else null), hours (float), priority (low/medium/high). If no deadline, set null. If no hours, estimate reasonably.
    Input: {user_input}
    """
    try:
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt
        )
        text = response.text.strip()
        # Remove markdown code blocks if present 
        import re
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```', '', text)
        return json.loads(text)
    except Exception as e:
        print(f"LLM error: {e}, falling back to regex")
        return parse_task_with_regex(user_input)

def parse_task_with_regex(user_input: str) -> Dict:
    """Simple regex fallback."""
 
    hours_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:hour|hr)s?', user_input, re.I)
    hours = float(hours_match.group(1)) if hours_match else 1.0
    
    # Look for priority keywords
    priority = "medium"
    if re.search(r'\b(high|urgent|asap|important)\b', user_input, re.I):
        priority = "high"
    elif re.search(r'\b(low|optional|maybe)\b', user_input, re.I):
        priority = "low"
    
    # Simple deadline : tomorrow, Friday, etc.
    deadline = None
    today = datetime.now().date()
    if "tomorrow" in user_input.lower():
        deadline = (today + timedelta(days=1)).isoformat()
    elif "friday" in user_input.lower():
        days_ahead = (4 - today.weekday()) % 7
        deadline = (today + timedelta(days=days_ahead)).isoformat()
       
    
    title = user_input[:50]  # naive logic
    return {
        "title": title,
        "deadline": deadline,
        "hours": hours,
        "priority": priority
    }

# ------------------------------
# Priority Score Calculation

def compute_priority_score(task: Dict, proc_risk: float = 0.0) -> float:
    """Higher score = higher priority."""
    now = datetime.now()
    deadline = datetime.fromisoformat(task["deadline"]) if task.get("deadline") else None
    
    # Urgency - inverse of  days left
    if deadline and deadline > now:
        days_left = (deadline - now).total_seconds() / 86400.0
        urgency = 1.0 / (days_left + 0.5)
    else:
        urgency = 2.0 if deadline and deadline <= now else 0.5  # overdue goes on top of list  
    
    # Effort - log scale: large tasks slightly higher
    effort = min(1.0, task["hours"] / 8.0)  # normalized
    
    # User hint
    hint_map = {"low": 0.2, "medium": 0.6, "high": 1.0}
    hint = hint_map.get(task.get("priority_hint", "medium"), 0.6)
    
    # risk factor - Procrastination
    risk = min(0.5, proc_risk * 0.1)
    
    # Weights
    score = (0.5 * urgency) + (0.2 * effort) + (0.3 * hint) + risk
    return score
    
# ------------------------------
# Productivity Learner (Simple)

def get_best_hours() -> List[Tuple[int, int]]:
    """Return list of (start_hour, end_hour) based on past focus ratings."""
    cursor.execute("SELECT hour_of_day, AVG(focus_rating) FROM productivity_logs GROUP BY hour_of_day")
    rows = cursor.fetchall()
    if not rows:
        # Default from user_preferences
        pref = cursor.execute("SELECT value FROM user_preferences WHERE key='preferred_hours'").fetchone()[0]
        blocks = pref.split(',')
        result = []
        for b in blocks:
            start, end = map(int, b.split('-'))
            result.append((start, end))
        return result
    
    # Hours with average focus > 3.5 are "best"
    best = [row[0] for row in rows if row[1] and row[1] > 3.5]
    # Convert consecutive hours into blocks
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

# ------------------------------
# Greedy Scheduler

def get_free_blocks(date: datetime.date, existing_events: List[Tuple[str, str]] = None) -> List[Tuple[datetime, datetime]]:
    """Return available time blocks for a given day."""
    best_hours = get_best_hours()
    free_blocks = []
    for start_hour, end_hour in best_hours:
        start = datetime(date.year, date.month, date.day, start_hour, 0)
        end = datetime(date.year, date.month, date.day, end_hour, 0)
        free_blocks.append((start, end))
    
    # Subtract existing events (simplified – in real app, parse from Google Calendar)
    if existing_events:
        for ev_start, ev_end in existing_events:
            ev_start_dt = datetime.fromisoformat(ev_start)
            ev_end_dt = datetime.fromisoformat(ev_end)
            new_blocks = []
            for blk_start, blk_end in free_blocks:
                if ev_end_dt <= blk_start or ev_start_dt >= blk_end:
                    new_blocks.append((blk_start, blk_end))
                else:
                    if blk_start < ev_start_dt:
                        new_blocks.append((blk_start, ev_start_dt))
                    if blk_end > ev_end_dt:
                        new_blocks.append((ev_end_dt, blk_end))
            free_blocks = new_blocks
    return free_blocks

def schedule_tasks(tasks: List[Dict], days_ahead: int = 7) -> List[Dict]:
    """Returns list of assignments: {task_id, title, start, end}"""
    # Sort by priority
    for t in tasks:
        t["priority_score"] = compute_priority_score(t, 0.0)  # get risk from DB 
    tasks_sorted = sorted(tasks, key=lambda x: x["priority_score"], reverse=True)
    
    schedule = []
    today = datetime.now().date()
    for day_offset in range(days_ahead):
        date = today + timedelta(days=day_offset)
        free_blocks = get_free_blocks(date)
        # assign tasks that fit
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
                    # Remove useless portion
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

# ------------------------------
# LLM Schedule Explainer

def explain_schedule(schedule: List[Dict]) -> str:
    if not HAS_GEMINI:
        return "AI explanation not available (google-genai not installed)."
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""
    You are a friendly study coach. Here is the user's schedule for today and upcoming days:
    {json.dumps(schedule, indent=2)}
    Write a short, motivational explanation (2-3 sentences) about why the hardest tasks are placed in certain time slots, and how this helps the student.
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',  # version 
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"Explanation error: {e}")
        return "I've built your schedule based on deadlines and your focus patterns. Check the tasks below."
# ------------------------------
# Main Interactive Loop

def add_task_from_input(user_input: str):
    parsed = parse_task_with_llm(user_input)
    if not parsed:
        print("Could not parse task.")
        return
    now_str = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO tasks (title, deadline, hours, priority_hint, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (parsed.get("title", "Untitled"), parsed.get("deadline"), 
          parsed.get("hours", 1.0), parsed.get("priority", "medium"), 
          "pending", now_str))
    conn.commit()
    print(f" Task added: {parsed['title']}")

def show_today_schedule():
    cursor.execute("SELECT id, title, deadline, hours, priority_hint, status FROM tasks WHERE status='pending'")
    tasks = [{"id": row[0], "title": row[1], "deadline": row[2], "hours": row[3], "priority_hint": row[4], "status": row[5]} for row in cursor.fetchall()]
    schedule = schedule_tasks(tasks, days_ahead=3)
    if not schedule:
        print("No pending tasks.")
        return
    print("\n Your AI-Generated Schedule:")
    for item in schedule[:10]:
        start = datetime.fromisoformat(item["start"])
        print(f"  {start.strftime('%a %H:%M')} – {item['title']} ({item['end']})")
    explanation = explain_schedule(schedule)
    print(f"\n Coach says: {explanation}\n")

def log_feedback(task_title: str, focus_rating: int, completed: bool = True):
    hour = datetime.now().hour
    today_str = datetime.now().date().isoformat()
    # Insert or update productivity log
    cursor.execute("""
        INSERT INTO productivity_logs (log_date, hour_of_day, focus_rating, tasks_completed)
        VALUES (?, ?, ?, ?)
    """, (today_str, hour, focus_rating, 1 if completed else 0))
    conn.commit()
    if completed:
        cursor.execute("UPDATE tasks SET status='done' WHERE title=?", (task_title,))
        conn.commit()
    print("Thanks for the feedback!")

def run_cli():
    print(" AI Smart Schedule & Task Prioritizer")
    print("Commands:")
    print("  add <your task description>")
    print("  show")
    print("  feedback <task_title> <focus_rating 1-5> [completed y/n]")
    print("  remind (manual check)")
    print("  exit")
    while True:
        cmd = input("\n> ").strip()
        if cmd.startswith("add "):
            add_task_from_input(cmd[4:])
        elif cmd == "show":
            show_today_schedule()
        elif cmd.startswith("feedback "):
            parts = cmd.split()
            if len(parts) >= 3:
                title = " ".join(parts[1:-1]) if len(parts) > 3 else parts[1]
                rating = int(parts[-2])
                completed = parts[-1].lower() == 'y'
                log_feedback(title, rating, completed)
            else:
                print("Usage: feedback <task_title> <rating> [y/n]")
        elif cmd == "remind":
            cursor.execute("SELECT id, title, deadline, hours, priority_hint, status FROM tasks WHERE status='pending'")
            tasks = [{"id": row[0], "title": row[1], "deadline": row[2], "hours": row[3], "priority_hint": row[4], "status": row[5]} for row in cursor.fetchall()]
            if not tasks:
                print(" No pending tasks. Nothing to remind.")
            else:
                sched = schedule_tasks(tasks, days_ahead=1)
                if not sched:
                    print(" Could not generate a schedule for tomorrow. Check your free time blocks or task deadlines.")
                else:
                    check_and_send_reminders(sched)
        elif cmd == "exit":
            break
        else:
            print("Unknown command.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "bot":
        asyncio.run(run_bot())
    else:
        run_cli()
