# AI-Smart-Schedule-Task-Prioritizer

A generative AI tool that helps students manage tasks, create optimized daily schedules, and receive intelligent reminders. It uses natural language processing, priority scoring, and adaptive learning to improve time management.

##  Features :

- **Natural Language Task Input** – Add tasks like *“Finish math homework by Friday, 2 hours, high priority”* – AI parses deadline, duration, and importance.
- **Smart Priority Scoring** – Combines urgency, effort, user hints, and past procrastination patterns.
- **AI-Powered Schedule Generation** – Places tasks into your best focus hours using a greedy scheduling algorithm.
- **Personalized Productivity Learning** – Learns your most productive hours from feedback (focus ratings 1–5).
- **Friendly AI Coach** – Explains *why* tasks are scheduled at certain times (Gemini LLM).
- **Flexible Storage** – SQLite database for tasks and productivity logs; no external DB setup.
- **Reminder System** – Console-based reminders (extendable to Telegram, email, etc.).
- **CLI Interface** – Simple command-line interaction.

##  Installation :

### 1. Clone or download the project
```bash
git clone https://github.com/yourusername/ai-smart-scheduler.git
cd ai-smart-scheduler
```

### 2. Create a virtual environment (recommended)
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate
```

### 3. Install required packages
```bash
pip install google-genai python-telegram-bot  # python-telegram-bot is optional
```

> **Note**: If you don’t want Telegram, just install `google-genai`.

### 4. Set up your Gemini API key
- Get a free API key from [Google AI Studio](https://aistudio.google.com/apikey).
- **Option A (recommended)**: Set environment variable
  - Windows (PowerShell): `$env:GEMINI_API_KEY="your-key-here"`
  - Mac/Linux: `export GEMINI_API_KEY="your-key-here"`
- **Option B (testing only)**: Hardcode in the script (replace `YOUR_GEMINI_API_KEY` in the code).

##  Usage :
Run the script:
```bash
python smart_scheduler.py
```

### Available Commands

| Command | Example | Description |
|---------|---------|-------------|
| `add <task description>` | `add write essay by tomorrow 10am, 2 hours` | Add a new task (AI parses deadline, effort, priority) |
| `show` | `show` | Display your AI-generated schedule for the next 3 days |
| `feedback <title> <rating> [y/n]` | `feedback math homework 4 y` | Rate your focus (1–5) and mark task as done – teaches the system |
| `remind` | `remind` | Check for upcoming tasks within 15 minutes (console) |
| `exit` | `exit` | Quit the application |


##  Working :

1. **Parsing** – Your sentence is sent to Gemini (or regex fallback) to extract title, deadline, hours, priority.
2. **Storage** – Tasks are saved in SQLite with status (pending/done).
3. **Priority Score** – Computed daily using:
   - Urgency (days left)
   - Effort (hours)
   - User priority hint
   - Historical procrastination factor
4. **Scheduling** – A greedy algorithm places high‑priority tasks into your best focus hours (learned from feedback).
5. **Explanation** – Gemini generates a motivational reason for the schedule.
6. **Learning** – Each feedback (`focus_rating`) updates the productivity logs, improving future schedules.

##  Project Structure :

```
ai-smart-scheduler/
│
├── smart_scheduler.py       # Main application
├── scheduler.db             # SQLite database (auto-created)
├── README.md                # This file
└── requirements.txt         # Dependencies
```

##  Future Scope :

-  Google Calendar read/write integration  
-  Full Telegram bot with inline buttons  
-  Mobile app (Flutter)  
-  Procrastination prediction with simple ML  
-  Collaborative scheduling for study groups  
-  Voice input (speech‑to‑text)
