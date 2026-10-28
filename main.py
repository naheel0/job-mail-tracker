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

from adapters.csv_store import load, save
from adapters.eml_parser import parse_dir
from adapters.ollama_client import OllamaClassifier
from services.classify import classify_all
from services.nudge import needs_followup, waiting_days
from services.track import merge

STATE_FILE = ROOT / ".state.json"  # label cache: email id -> {label, company, role}


def _load_state() -> dict:
    return json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}


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


def main(folder: Path = ROOT / "inbox") -> None:
    records = parse_dir(folder)
    if not records:
        print(f"No .eml files found in {folder}/")
        return

    state = _load_state()
    new = [r for r in records if r.id not in state]
    if new:
        print(f"Classifying {len(new)} new email(s) with Ollama ({OllamaClassifier.__name__})...")
        for rec in classify_all(new, OllamaClassifier()):
            state[rec.id] = {"label": rec.label, "company": rec.company, "role": rec.role}
        STATE_FILE.write_text(json.dumps(state, indent=1), encoding="utf-8")

    for rec in records:  # fill every record from cache (old + just-classified)
        cached = state.get(rec.id)
        if cached:
            rec.label, rec.company, rec.role = cached["label"], cached["company"], cached["role"]

    rows = merge(load(), records)
    save(rows)
    print(f"Saved tracker.csv ({len(rows)} rows), processed {len(records)} email(s), "
          f"{len(new)} newly classified.")
    report(rows)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "inbox")
