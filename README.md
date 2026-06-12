#  AI Smart Schedule & Task Prioritizer

A generative AI‑powered study companion that helps students manage tasks, create optimized daily schedules, and improve productivity through personalized feedback.  
The app uses **Google Gemini AI** to understand natural language tasks, learns your best focus hours, and explains its scheduling decisions like a friendly coach.

---

##  Features :

- **Natural Language Task Input** – Just type *“Math homework due Friday, 2 hours, high priority”* – AI extracts deadline, duration, and priority.
- **Smart Priority Scoring** – Combines urgency, effort, user hints, and past procrastination patterns.
- **AI‑Powered Schedule Generation** – Places tasks into your best focus hours using a greedy scheduling algorithm.
- **Personalized Productivity Learning** – Learns your most productive hours from your feedback (focus ratings 1–5).
- **Friendly AI Coach** – Explains *why* tasks are scheduled at certain times (Gemini LLM).
- **Web Interface** – Built with Streamlit – no installation required, works on any device.
- **Persistent Storage** – SQLite database stores tasks and productivity logs.
- **Feedback Loop** – Rate completed tasks to improve future schedules.

---

##  Tech Stack :

| Component         | Technology |
|------------------|------------|
| Frontend / UI    | Streamlit |
| AI / LLM         | Google Gemini (`google-genai` SDK) |
| Scheduling       | Custom greedy priority algorithm |
| Database         | SQLite |
| Language         | Python 3.9+ |
| Data Handling    | Pandas (optional, for display) |

---

##  Installation (Local) :

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/ai-smart-scheduler.git
   cd ai-smart-scheduler
   ```

2. **Create a virtual environment (recommended)**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Mac/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up your Gemini API key**
   - Get a free key from [Google AI Studio](https://aistudio.google.com/apikey)
   - Create a `.streamlit/secrets.toml` file in the project root with:
     ```toml
     GEMINI_API_KEY = "your-actual-api-key"
     ```

5. **Run the app**
   ```bash
   streamlit run app.py
   ```

---
 
##  Deployment (Streamlit Cloud) :

1. Push your code to a **GitHub repository**.
2. Go to [Streamlit Cloud](https://streamlit.io/cloud), sign in with GitHub.
3. Click **New app**, select your repo, branch, and set `app.py` as the main file.
4. Under **Advanced settings** → **Secrets**, add:
   ```
   GEMINI_API_KEY = "your-actual-api-key"
   ```
5. Click **Deploy**. Your app will be live at `https://your-app-name.streamlit.app`

---


##  How It Works :

1. **Parsing** – Your task description is sent to Gemini (or regex fallback) to extract:
   - Title, deadline, estimated hours, priority.
2. **Storage** – Tasks are saved in an SQLite database.
3. **Priority Score** – Each pending task gets a score based on:
   - **Urgency** = 1 / (days left + 0.5)
   - **Effort** = normalized hours (max 8h)
   - **User priority** (low/medium/high)
   - **Procrastination risk** (learned from past delays)
4. **Scheduling** – A greedy algorithm places higher‑priority tasks into your best focus hours (learned from feedback).
5. **Explanation** – Gemini generates a motivational reason for the schedule.
6. **Learning** – Each feedback (focus rating) updates the productivity logs, improving future schedules.

---

##  Project Structure :

```
ai-smart-scheduler/
├── app.py                  # Streamlit web application
├── requirements.txt        # Python dependencies
├── scheduler.db            # SQLite database (auto-created)
├── README.md               # This file

```

---

- [Google Gemini API](https://ai.google.dev) for AI capabilities
- [Streamlit](https://streamlit.io) for the amazing web framework
- All students who tested the early prototypes
