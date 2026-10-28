"""Issue 6: which applications need a nudge? Pure rule, zero I/O, fixed dates.

Rule: status 'applied' (or still blank) and last contact older than N days.

Run:  python services/nudge.py    (self-check with fixed dates)
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root

DEFAULT_DAYS = 7


def _last_contact(row: dict) -> date | None:
    raw = (row.get("last_contact") or "")[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None  # ponytail: unparsable date -> not nudgeable, never crash


def waiting_days(row: dict, today: date) -> int | None:
    last = _last_contact(row)
    return (today - last).days if last else None


def needs_followup(rows: list[dict], today: date, days: int = DEFAULT_DAYS) -> list[dict]:
    """Rows where an application is silent for >= days. Sorted: oldest waiting first."""
    flagged = []
    for row in rows:
        if row.get("status") not in ("applied", ""):
            continue  # interviewing / rejected / offer: nothing to chase
        wait = waiting_days(row, today)
        if wait is not None and wait >= days:
            flagged.append(row)
    return sorted(flagged, key=lambda r: r.get("last_contact") or "")


def _self_check() -> None:
    def row(company, status, last):
        return {"company": company, "role": "Dev", "status": status, "last_contact": last}

    today = date(2026, 10, 28)
    rows = [
        row("OldCo", "applied", "2026-10-01"),      # 27d silent -> flag
        row("FreshCo", "applied", "2026-10-27"),     # 1d -> no
        row("Ghosted", "applied", "2026-10-20"),     # 8d -> flag
        row("Talking", "interviewing", "2026-10-01"),  # in progress -> no
        row("NoDate", "applied", ""),                # unparsable -> no
    ]
    flagged = needs_followup(rows, today, days=7)
    assert [r["company"] for r in flagged] == ["OldCo", "Ghosted"], flagged
    assert waiting_days(rows[0], today) == 27
    assert waiting_days(rows[4], today) is None
    assert needs_followup(rows, today, days=30) == []  # threshold respected
    print("OK: nudge (flag stale applied, skip fresh/in-progress/bad-date, threshold) passed")


if __name__ == "__main__":
    _self_check()
