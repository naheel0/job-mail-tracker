"""Issue 7: the CLI. Wires parse -> classify -> track -> nudge -> report. No logic here.

Run:  python main.py [folder]     (default: inbox/)
Classified results are cached in .state.json, so re-runs need no Ollama and no internet.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from adapters.csv_store import atomic_write, load, save
from adapters.eml_parser import parse_dir
from adapters.ollama_client import OllamaClassifier
from services.nudge import needs_followup, waiting_days
from services.track import merge

STATE_FILE = ROOT / ".state.json"  # label cache: email id -> {label, company, role}


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:  # crash mid-write left a truncated file: emails re-classify, nothing lost
        STATE_FILE.rename(STATE_FILE.with_suffix(".json.bak"))
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
    # ponytail: data.js instead of fetch(tracker.csv) - file:// blocks fetch, double-click must work
    atomic_write(ROOT / "ui" / "data.js",
                 "window.TRACKER_DATA = " + json.dumps(rows, indent=1) + ";\n")
    return rows


def main(folder: Path = ROOT / "inbox", with_sync: bool = False) -> None:
    if with_sync:
        from adapters.imap_fetch import sync
        print(f"Syncing IMAP -> {folder}/ ...")
        print(f"Fetched {sync(folder)} new email(s) (deduped by Message-ID).")

    records = parse_dir(folder)
    if not records:
        print(f"No .eml files found in {folder}/")
        return

    state = _load_state()
    new = [r for r in records if r.id not in state]
    if new:
        print(f"Classifying {len(new)} new email(s) with Ollama...", flush=True)
        clf = OllamaClassifier()
        done_count = fails = 0
        try:
            for rec in new:
                try:
                    done = clf.classify(rec)
                except Exception as exc:  # one bad email != lost batch
                    fails += 1
                    print(f"  skip {rec.subject[:40]!r}: {exc}", file=sys.stderr, flush=True)
                    if fails >= 5:  # Ollama is down/broken, not one weird email - stop
                        raise SystemExit(f"{fails} emails in a row failed - giving up. "
                                         f"Progress saved, fix Ollama and re-run.") from exc
                    continue
                fails = 0
                done_count += 1
                state[done.id] = {"label": done.label, "company": done.company, "role": done.role}
                if done_count % 10 == 0:
                    atomic_write(STATE_FILE, json.dumps(state, indent=1))
                    _publish(records, state)  # UI grows live
                    print(f"  {done_count}/{len(new)} classified", flush=True)
        except (KeyboardInterrupt, SystemExit) as exc:  # Ctrl+C or Ollama died: keep everything so far
            atomic_write(STATE_FILE, json.dumps(state, indent=1))
            rows = _publish(records, state)
            print(f"\nStopped early ({done_count}/{len(new)} classified this run) - "
                  f"progress saved, dashboard updated. Re-run to continue.", file=sys.stderr)
            raise SystemExit(130 if isinstance(exc, KeyboardInterrupt) else str(exc) or 1)
        atomic_write(STATE_FILE, json.dumps(state, indent=1))

    rows = _publish(records, state)
    print(f"Saved tracker.csv ({len(rows)} rows), processed {len(records)} email(s), "
          f"{len(new)} newly classified.")
    report(rows)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--sync"]
    main(Path(args[0]) if args else ROOT / "inbox", with_sync="--sync" in sys.argv)
