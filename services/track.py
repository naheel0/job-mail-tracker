"""Issue 5: merge labeled records into tracker rows. Pure logic, zero I/O.

Rules:
- one row per (company, role)
- newest contact date wins
- status transitions: applied -> interviewing -> rejected | offer (never backwards)
- records without a company can't be tracked -> skipped

Run:  python services/track.py    (self-check with fixed dates)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root

from core.models import EmailRecord
from email.utils import parseaddr

# label -> status (None = no status change, e.g. followups and newsletters)
STATUS_BY_LABEL = {
    "applied": "applied",
    "recruiter": "applied",
    "interview": "interviewing",
    "rejected": "rejected",
    "offer": "offer",
    "followup": None,
    "noise": None,
}
RANK = {"": 0, "applied": 1, "interviewing": 2, "rejected": 3, "offer": 4}


def _key(row: dict) -> tuple[str, str]:
    return (row["company"].lower(), (row.get("role") or "").lower())


def merge(existing: list[dict], records: list[EmailRecord]) -> list[dict]:
    rows = {_key(r): dict(r) for r in existing}
    for rec in sorted(records, key=lambda r: r.date):  # oldest first -> newest wins
        if not rec.company:
            continue  # ponytail: unidentifiable sender = nothing to track
        status = STATUS_BY_LABEL.get(rec.label, "")
        row = rows.setdefault(_key({"company": rec.company, "role": rec.role or ""}),
                              {"company": rec.company, "role": rec.role or "",
                               "status": "", "last_contact": ""})
        row["last_contact"] = rec.date
        row["email"] = parseaddr(rec.from_addr)[1] or row.get("email", "")  # newest sender wins
        if status and RANK[status] >= RANK.get(row["status"], 0):  # never move backwards
            row["status"] = status
    for row in rows.values():
        row.setdefault("email", "")  # rows from an old CSV (pre-email column)
    return sorted(rows.values(), key=_key)


def _self_check() -> None:
    def mail(cid, company, role, label, date):
        return EmailRecord(cid, "x@y.z", "s", date, "b", label=label,
                           company=company, role=role)

    # happy path: applied -> interview advances, newest date wins
    out = merge([], [mail("1", "Acme", "Dev", "applied", "2026-10-01"),
                     mail("2", "Acme", "Dev", "interview", "2026-10-05")])
    assert len(out) == 1 and out[0]["status"] == "interviewing", out
    assert out[0]["last_contact"] == "2026-10-05"

    # never downgrade: rejected(6th) then old applied(2nd) -> stays rejected
    out = merge([], [mail("3", "Beta", "QA", "rejected", "2026-10-06"),
                     mail("4", "Beta", "QA", "applied", "2026-10-02")])
    assert out[0]["status"] == "rejected" and out[0]["last_contact"] == "2026-10-06", out

    # merge with existing row + skip companyless + noise doesn't touch status
    existing = [{"company": "Acme", "role": "Dev", "status": "applied",
                 "last_contact": "2026-10-01"}]
    out = merge(existing, [mail("5", None, None, "noise", "2026-10-07"),
                           mail("6", "Acme", "Dev", "followup", "2026-10-07")])
    assert len(out) == 1 and out[0]["status"] == "applied"          # unchanged
    assert out[0]["last_contact"] == "2026-10-07"                   # date bumped
    assert out[0]["email"] == "x@y.z"                               # sender captured
    print("OK: merge (advance, never-downgrade, skip, merge-existing) passed")


if __name__ == "__main__":
    _self_check()
