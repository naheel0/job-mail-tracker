# Job Mail Tracker

Local-first email assistant for job hunters. Reads an exported inbox (`.eml` files), classifies every email with a **local open-source AI model**, and turns it into an actionable tracker — no cloud, no API, your job search stays on your machine.

> **DEV post hook:** Your job search shouldn't be someone else's training data.

## What it does

1. **Sort** — labels each email: application confirmation, recruiter outreach, interview invite, rejection, offer, follow-up, platform promo (job alerts/digests — hidden by default in the dashboard), noise
2. **Track** — maintains `tracker.csv`: company, role, status, last contact date
3. **Nudge** — flags applications with no reply after N days
4. **(Optional) Sync** — `--sync` pulls new mail over IMAP (any provider): received into `inbox/`, **sent** into `sent/` — so follow-ups you wrote stop the nudge clock too

## Usage

```powershell
# once: install Ollama, then
ollama pull llama3.2:3b

# put .eml files in inbox/  (Gmail: open email -> ... -> Show original -> Download message)

python main.py              # parse -> classify (local model) -> tracker.csv -> report
python main.py --sync       # optional: pull new mail over IMAP first (needs .env, see below)
```

Open `ui/index.html` (double-click) for the dashboard: status filters, follow-up badges, waiting days, a `promo` filter for platform job alerts (hidden from the main list by default), an `unfiltered` view showing every mail inbox-style (From / Subject / Date / Label), and a `sent` view listing only mail you sent — newest activity first, like a real inbox.

**IMAP sync (optional)** — create `.env` (gitignored):

```
IMAP_HOST=imap.gmail.com
IMAP_USER=you@gmail.com
IMAP_PASSWORD=your-app-password   # Gmail: 2-Step Verification -> App passwords
```

Works with any **OpenAI-compatible endpoint** — local (Ollama, LM Studio, llama.cpp server) or
cloud (Groq, OpenRouter, …). Defaults to local Ollama, so out of the box nothing leaves your machine:

```powershell
# examples - put in .env (or as env vars), then just run python main.py
# LLM_BASE_URL=http://localhost:1234/v1                                    # LM Studio
# LLM_BASE_URL=https://api.groq.com/openai/v1  LLM_MODEL=llama-3.1-8b-instant  LLM_API_KEY=gsk_...   # Groq
```

Works with any IMAP provider (Outlook, Yahoo, …). Each email is classified **once** —
results cache in `.state.json`, so re-runs need no model and no internet.

## Why open innovation matters here

- Works fully **offline** — no internet required
- **Private** — job search data never leaves your machine
- **Free to run** — no API costs
- **Swappable** — any open-weight model or provider, via config only (no code changes)

## Stack

- Python 3.11+ (stdlib `email` for parsing)
- Any OpenAI-compatible LLM endpoint — defaults to [Ollama](https://ollama.com) with an open-weight model (llama 3.2)
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
