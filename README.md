# Lab Works Tracking Hub

A collaborative Streamlit web application for lab leads and students to capture goals, daily activities, and team-wide progress. Students can set milestones, mentors can monitor everyone at a glance, and Groq's API can polish updates whenever you need a well-written status.

## Key features
- 🔐 Simple authentication (student or mentor role) stored in a local SQLite database.
- 🎯 Goal management with visibility controls (public/private) and status tracking.
- 📓 Activity log per goal with progress percentages and AI-assisted writing using your Groq API key.
- 📰 Shared feed that surfaces public updates plus private ones for their authors (mentors see everything).
- 📊 Insights tab with charts, upcoming deadlines, and a CSV export for reporting or backups.

## Project structure
```
lab works tracking/
├── streamlit_app.py        # Main Streamlit UI
├── database.py             # SQLite helpers and queries
├── groq_client.py          # Groq API wrapper
├── requirements.txt        # Python dependencies
├── .gitignore              # Keeps secrets / db files out of GitHub
└── .streamlit/
    └── secrets.example.toml
```

## Getting started locally
1. **Create a virtual environment** (Python 3.10+).
   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # on Windows
   # or source .venv/bin/activate on macOS/Linux
   ```
2. **Install dependencies.**
   ```bash
   pip install -r requirements.txt
   ```
3. **Add your Groq credentials.**
   Copy `.streamlit/secrets.example.toml` to `.streamlit/secrets.toml` (or set environment variables) and place your rotated key:
   ```toml
   GROQ_API_KEY = "gsk_your_new_key"
   GROQ_MODEL = "llama3-8b-8192"  # optional override
   ```
4. **Run the app.**
   ```bash
   streamlit run streamlit_app.py
   ```
   The first run creates `labworks.db` in the project root. Every time you register/log in from Streamlit, the credentials are saved there.

## Deploying on Streamlit Community Cloud
1. Push this folder to a GitHub repository (public or private).
2. On [share.streamlit.io](https://share.streamlit.io), click **Deploy an app** → choose your repo and the branch containing `streamlit_app.py`.
3. In the *Advanced settings → Secrets* panel, add:
   ```toml
   GROQ_API_KEY="gsk_your_rotated_key"
   GROQ_MODEL="llama3-8b-8192"
   ```
4. Streamlit Cloud automatically installs `requirements.txt` and launches the app.

> **Note:** Streamlit Cloud keeps the SQLite file on disk, but it's not suited for high-concurrency writes. If you expect heavy simultaneous usage, plug in a hosted Postgres/Supabase instance and update `database.py` accordingly.

## Using the Groq integration
- Groq calls happen only when a user presses the “Polish” buttons in the UI.
- API errors are surfaced inline without exposing secrets; keys are loaded from environment variables or `st.secrets`.
- Rotate the key you pasted earlier—never commit real keys to GitHub. `.gitignore` already excludes `.streamlit/secrets.toml` and the SQLite database.

## Next ideas
- Add email / SSO authentication via an identity provider.
- Hook up notifications (Slack/Teams) when goals stay “Stuck” for too long.
- Connect to GitHub Classroom or other tooling for automatic progress snapshots.
- Swap SQLite for a hosted database if multiple teachers will use the tool simultaneously.

Happy tracking!
