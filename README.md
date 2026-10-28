# Job Mail Tracker

Local-first email assistant for job hunters. Reads an exported inbox (`.eml` files), classifies every email with a **local open-source AI model**, and turns it into an actionable tracker — no cloud, no API, your job search stays on your machine.

> **DEV post hook:** Your job search shouldn't be someone else's training data.

## What it does

1. **Sort** — labels each email: application confirmation, recruiter outreach, interview invite, rejection, offer, follow-up, noise
2. **Track** — maintains `tracker.csv`: company, role, status, last contact date
3. **Nudge** — flags applications with no reply after N days
4. **(Optional) Sync** — `--sync` pulls new mail over IMAP (any provider) straight into `inbox/`, no manual export

## Usage

```powershell
# once: install Ollama, then
ollama pull llama3.2:3b

# put .eml files in inbox/  (Gmail: open email -> ... -> Show original -> Download message)

python main.py              # parse -> classify (local model) -> tracker.csv -> report
python main.py --sync       # optional: pull new mail over IMAP first (needs .env, see below)
```

Open `ui/index.html` (double-click) for the dashboard: status filters, follow-up badges, waiting days.

**IMAP sync (optional)** — create `.env` (gitignored):

```
IMAP_HOST=imap.gmail.com
IMAP_USER=you@gmail.com
IMAP_PASSWORD=your-app-password   # Gmail: 2-Step Verification -> App passwords
```

Works with any IMAP provider (Outlook, Yahoo, …). Each email is classified **once** —
results cache in `.state.json`, so re-runs need no model and no internet.

## Why open innovation matters here

- Works fully **offline** — no internet required
- **Private** — job search data never leaves your machine
- **Free to run** — no API costs
- **Swappable** — change the model with one config value

## Stack

- Python 3.11+ (stdlib `email` for parsing)
- [Ollama](https://ollama.com) with an open-weight model (llama 3.2 / mistral)
- CSV storage (no database)
- HTML dashboard (no build step, no server)

## Docs

- [System Design](SYSTEM_DESIGN.md)
- [Development Plan](PLAN.md)

## Hacktoberfest 2026

- Challenge: Hacktoberfest Open-Source AI Challenge — Week 4 ("Ghost in the Machine")
- Deadline: October 31, 2026, 11:59 PM PDT
- Tags: `#devchallenge` `#hf26challenge`
- Author: naheel0
