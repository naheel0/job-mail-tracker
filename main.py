"""Issue 7: the CLI. Wires parse -> classify -> track -> nudge -> report. No logic here.

Run:  python main.py [folder]     (default: inbox/)
Classified results are cached in .state.json, so re-runs need no LLM and no internet.
LLM endpoint/model: LLM_BASE_URL / LLM_MODEL / LLM_API_KEY env vars (any OpenAI-compatible API).
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _load_dotenv() -> None:
    """4-line .env loader: LLM_*/IMAP_* work from the file, not just the shell."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())  # real env vars win


_load_dotenv()  # must run before the adapter import (it reads env at import time)

from adapters.csv_store import atomic_write, load, save
from adapters.eml_parser import parse_dir
from adapters.llm_client import LLMClassifier, MODEL
from services.nudge import needs_followup, waiting_days
from services.track import merge

STATE_FILE = ROOT / ".state.json"  # label cache: email id -> {label, company, role}

# live LLM run state, published into ui/data.js so the dashboard can show AI progress
AI_RUN = {"running": False, "done": 0, "total": 0, "ts": ""}


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:  # crash mid-write left a truncated file: emails re-classify, nothing lost
        STATE_FILE.replace(STATE_FILE.with_suffix(".json.bak"))  # replace: overwrite an older .bak
        print(f"WARNING: .state.json was corrupt - backed up to .state.json.bak, starting fresh",
              file=sys.stderr)
        return {}


def report(rows: list[dict]) -> None:
    counts = Counter(r["status"] or "unclassified" for r in rows)
    summary = ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))
    print(f"\nTracker: {len(rows)} row(s) - {summary or 'empty'}")

    flagged = needs_followup(rows, date.today())
    if not flagged:
        print("Nothing to chase today.")
        return
    print("Needs follow-up:")
    for row in flagged:
        wait = waiting_days(row, date.today())
        print(f"  - {row['company']} / {row['role'] or '?'} - {wait}d silent since "
              f"{row['last_contact'][:10]}")


def _publish(records, state) -> list[dict]:
    """Fill records from cache, merge, write CSV + data.js. Called every 10 emails so the
    dashboard fills up DURING long runs, not only at the end."""
    for rec in records:
        cached = state.get(rec.id)
        if cached:
            rec.label, rec.company, rec.role = cached["label"], cached["company"], cached["role"]
    rows = merge(load(), records)
    save(rows)
    # inbox view: every parsed mail (no bodies) for the 'unfiltered' filter
    mails = [{"from": r.from_addr, "to": r.to_addr, "subject": r.subject, "date": r.date,
              "label": r.label, "company": r.company, "dir": r.direction}
             for r in sorted(records, key=lambda r: r.date, reverse=True)]
    # ponytail: data.js instead of fetch(tracker.csv) - file:// blocks fetch, double-click must work
    AI_RUN["ts"] = datetime.now().isoformat(timespec="seconds")  # freshness stamp for the UI
    ai = {"total": len(records), "classified": sum(1 for r in records if r.id in state),
          "model": MODEL, "run": dict(AI_RUN)}
    atomic_write(ROOT / "ui" / "data.js",
                 "window.TRACKER_DATA = " + json.dumps(rows, indent=1) + ";\n"
                 + "window.MAIL_DATA = " + json.dumps(mails, indent=1) + ";\n"
                 + "window.AI_STATS = " + json.dumps(ai) + ";\n")
    return rows


def main(folder: Path = ROOT / "inbox", with_sync: bool = False) -> None:
    if with_sync:
        from adapters.imap_fetch import sync
        print(f"Syncing IMAP -> {folder}/ ...")
        print(f"Fetched {sync(folder)} new email(s) (deduped by Message-ID).")

    records = parse_dir(folder) + parse_dir(ROOT / "sent", "sent")  # sent/ may not exist yet
    if not records:
        print(f"No .eml files found in {folder}/")
        return

    state = _load_state()
    new = [r for r in records if r.id not in state]
    done_count = 0
    if new:
        print(f"Classifying {len(new)} new email(s) with {MODEL}...", flush=True)
        AI_RUN.update(running=True, done=0, total=len(new))
        clf = LLMClassifier()
        fails = 0
        try:
            for rec in new:
                try:
                    done = clf.classify(rec)
                except Exception as exc:  # one bad email != lost batch
                    # note: _generate raises SystemExit for connection problems, which
                    # bypasses this and stops at email #1 (fail-fast). This counter is
                    # for systematic per-email failures (e.g. a bug in answer parsing).
                    fails += 1
                    print(f"  skip {rec.subject[:40]!r}: {exc}", file=sys.stderr, flush=True)
                    if fails >= 5:
                        raise SystemExit(f"{fails} emails in a row failed - giving up. "
                                         f"Progress saved, fix the cause and re-run.") from exc
                    continue
                fails = 0
                done_count += 1
                state[done.id] = {"label": done.label, "company": done.company, "role": done.role}
                if done_count % 10 == 0:
                    atomic_write(STATE_FILE, json.dumps(state, indent=1))
                    AI_RUN["done"] = done_count
                    _publish(records, state)  # UI grows live
                    print(f"  {done_count}/{len(new)} classified", flush=True)
        except (KeyboardInterrupt, SystemExit) as exc:  # Ctrl+C or Ollama died: keep everything so far
            atomic_write(STATE_FILE, json.dumps(state, indent=1))
            AI_RUN.update(running=False, done=done_count)
            _publish(records, state)
            print(f"\nStopped early ({done_count}/{len(new)} classified this run) - "
                  f"progress saved, dashboard updated. Re-run to continue.", file=sys.stderr)
            raise SystemExit(130 if isinstance(exc, KeyboardInterrupt) else str(exc) or 1)
        atomic_write(STATE_FILE, json.dumps(state, indent=1))
        AI_RUN.update(running=False, done=done_count)  # run over: chip stops pulsing

    rows = _publish(records, state)
    print(f"Saved tracker.csv ({len(rows)} rows), processed {len(records)} email(s), "
          f"{done_count} newly classified.")
    report(rows)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--sync"]
    main(Path(args[0]) if args else ROOT / "inbox", with_sync="--sync" in sys.argv)
