# Job Mail Tracker

Local-first email assistant for job hunters. Reads an exported inbox (`.eml` files), classifies every email with a **local open-source AI model**, and turns it into an actionable tracker — no cloud, no API, your job search stays on your machine.

> **DEV post hook:** Your job search shouldn't be someone else's training data.

## What it does

1. **Sort** — labels each email: application confirmation, recruiter outreach, interview invite, rejection, offer, follow-up, noise
2. **Track** — maintains `tracker.csv`: company, role, status, last contact date
3. **Nudge** — flags applications with no reply after N days
4. **(Optional) Sync** — `--sync` pulls new mail over IMAP (any provider) straight into `inbox/`, no manual export

## Why open innovation matters here

- Works fully **offline** — no internet required
- **Private** — job search data never leaves your machine
- **Free to run** — no API costs
- **Swappable** — change the model with one config value

## Stack

- Python 3.11+ (stdlib `email` for parsing)
- [Ollama](https://ollama.com) with an open-weight model (llama 3.2 / mistral)
- CSV storage (no database)
- TS/HTML dashboard (reads `tracker.csv`)

## Docs

- [System Design](SYSTEM_DESIGN.md)
- [Development Plan](PLAN.md)

## Hacktoberfest 2026

- Challenge: Hacktoberfest Open-Source AI Challenge — Week 4 ("Ghost in the Machine")
- Deadline: October 31, 2026, 11:59 PM PDT
- Tags: `#devchallenge` `#hf26challenge`
- Author: naheel0
