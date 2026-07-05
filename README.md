# 🤖 AI Job Hunting Agent (Job Bot MVP)

An end-to-end local AI-powered agent that automates job discovery, ranks opportunities against your resume, tailors applications, fills web forms, monitors your inbox, and notifies you via Telegram.

---

## 🚀 Features

- **Multi-Source Scraping**: Discover jobs concurrently from 7+ platforms (RemoteOK, Remotive, WWR, Greenhouse, Lever, Ashby, Y Combinator/HackerNews).
- **AI Matching**: Automatically parse your resume PDF and calculate match scores (0-100%) with custom summaries (✓ Met / ✗ Missing requirements).
- **Resume Tailoring**: Adjust summaries, highlight projects, and align skill order dynamically for each role. Generates personalized cover letters.
- **Application Assistant**: Pre-fills web application forms in a headed browser using Playwright, pausing for user approval before submission.
- **Gmail Monitor**: OAuth2 integration to poll, classify (Interview, Rejection, Offer, OA), and update status on the tracker.
- **Telegram Bot**: Sends real-time notifications for interview invitations and high-score opportunities.
- **Premium Web Dashboard**: Manage target companies, upload resumes, filter job listings, and drag-and-drop status boards.

---

## 🛠️ Setup Instructions

### 1. Installation

Ensure you have Python 3.11+ installed. Clone or copy this workspace, then run:

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies (including developer tools)
pip install -e .[dev]

# Install Playwright browser engines (one-time setup)
playwright install chromium
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and fill out your variables:

```bash
cp .env.example .env
```

Set your OpenAI-compatible API credentials (`AI_BASE_URL` and `AI_API_KEY`) to connect to your preferred LLM provider (Ollama, OpenAI, Groq, Together, etc.).

---

## ✉️ Integrations Setup

### 1. Telegram Notifications

1. Search for `@BotFather` in Telegram and start a chat.
2. Send `/newbot` and follow the instructions to get your **HTTP API Token**.
3. Paste the token into `TELEGRAM_BOT_TOKEN` in your `.env`.
4. Open a chat with your new bot and click **Start** or send a message.
5. Retrieve your chat ID by opening the following URL in a browser:
   `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
6. Locate the `"chat":{"id":...}` value in the JSON response and paste it into `TELEGRAM_CHAT_ID` in `.env`.

### 2. Gmail Inbox Monitoring

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project and navigate to the **API Library**.
3. Search for and enable the **Gmail API**.
4. Go to **OAuth Consent Screen**:
   - Choose **External** user type.
   - Fill in app details, add scope: `https://www.googleapis.com/auth/gmail.modify` and `https://www.googleapis.com/auth/gmail.readonly`.
   - Add your Gmail account as a **Test User** (important while in publishing sandbox mode).
5. Navigate to **Credentials** -> **Create Credentials** -> **OAuth Client ID**:
   - Select application type: **Desktop App**.
   - Download the generated JSON client secrets file.
6. Rename it to `gmail_credentials.json` and place it in the `data/` directory (created after database initialization).
7. Upon first running the email monitor, a browser page will open requesting consent. Log in, authorize, and `token.json` will cache automatically.

---

## 🎮 CLI Usage

Initialize the database, folders, and seed companies first:
```bash
job-bot init-db
```

Parse and structure your primary resume PDF:
```bash
job-bot parse-resume --path /path/to/resume.pdf
```

Manually scrape listings from all sources:
```bash
job-bot scrape
```

Calculate match scores on scraped job descriptions:
```bash
job-bot match
```

Launch the headed form filler browser assistant for a specific job:
```bash
job-bot apply <job_id>
```

Start the background scheduler thread (runs cron-tasks periodically):
```bash
job-bot scheduler
```

Start the full system (Web Dashboard API + Background Scheduler together):
```bash
job-bot full
```
Open your browser and navigate to `http://127.0.0.1:8000` to view the dashboard!

---

## 🧪 Running Tests

To run the automated test suite, activate your virtual environment and execute:

```bash
pytest tests/ -v
```
