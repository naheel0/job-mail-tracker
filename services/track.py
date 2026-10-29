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
from email.utils import getaddresses

# label -> status (None = no status change, e.g. followups and newsletters)
STATUS_BY_LABEL = {
    "applied": "applied",
    "recruiter": "applied",
    "interview": "interviewing",
    "rejected": "rejected",
    "offer": "offer",
    "followup": None,
    "promo": "promo",   # pseudo-status: visible badge, never chased, never outranks real states
    "noise": None,
}
RANK = {"": 0, "applied": 1, "interviewing": 2, "rejected": 3, "offer": 4, "promo": 0}


def _key(row: dict) -> tuple[str, str]:
    # .get guards corrupt CSV rows (company=None would crash .lower())
    return ((row.get("company") or "").strip().lower(),
            (row.get("role") or "").strip().lower())


def merge(existing: list[dict], records: list[EmailRecord]) -> list[dict]:
    rows = {_key(r): dict(r) for r in existing}
    for rec in sorted(records, key=lambda r: r.date):  # oldest first -> newest wins
        if not rec.company or rec.label == "noise":
            continue  # no company, or noise: nothing to track (promo handled below)
        status = STATUS_BY_LABEL.get(rec.label, "")
        key = _key({"company": rec.company, "role": rec.role or ""})
        fresh = key not in rows
        row = rows.setdefault(key, {"company": rec.company, "role": rec.role or "",
                                    "status": "", "last_contact": ""})
        if rec.label != "promo" or fresh:
            # promo keeps its own arrival date only on a fresh row - it never
            # resets the silence clock of a real application
            row["last_contact"] = rec.date
            # direction of the mail that set last_contact = who spoke last
            row["dir"] = rec.direction
            # contact = the other party: sent mail -> recipient, received -> sender
            peer = rec.to_addr if rec.direction == "sent" else rec.from_addr
            # getaddresses (list form): multi-recipient To: "a@x, b@x" yields the
            # first address - parseaddr is strict in py3.13+ and returns "" there
            got = getaddresses([peer])
            row["email"] = (got[0][1] if got else "") or row.get("email", "")
        if status and RANK[status] >= RANK.get(row["status"], 0):  # never move backwards
            row["status"] = status
    # direction of the mail that set last_contact = who spoke last
    dirs = {(_key({"company": r.company, "role": r.role or ""}), r.date): r.direction
            for r in records if r.company and r.label != "noise"}
    for row in rows.values():
        row.setdefault("email", "")  # rows from an old CSV (pre-email column)
        if not row.get("dir"):
            # old CSV rows + promo-only rows (promo never re-enters the branch):
            # recover the direction of the record that set last_contact (same key+date)
            row["dir"] = dirs.get((_key(row), row.get("last_contact") or ""), "")
    # inbox order: most recent send/receive first (date+time, ISO = true
    # chronological string order); rows with no date sink to the bottom.
    # "" sorts smallest, so reverse=True puts empty dates last.
    return sorted(rows.values(), key=lambda r: r.get("last_contact") or "",
                  reverse=True)


def _self_check() -> None:
    def mail(cid, company, role, label, date):
        return EmailRecord(cid, "x@y.z", "s", date, "b", label=label,
                           company=company, role=role)

    # happy path: applied -> interview advances, newest date wins
    out = merge([], [mail("1", "Acme", "Dev", "applied", "2026-10-01"),
                     mail("2", "Acme", "Dev", "interview", "2026-10-05")])
    assert len(out) == 1 and out[0]["status"] == "interviewing", out
    assert out[0]["last_contact"] == "2026-10-05"
    assert out[0]["dir"] == "inbox"        # newest mail was received

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

    # noise with company -> no row at all (promo mail must not pollute the tracker)
    out = merge([], [mail("7", "Google", None, "noise", "2026-10-07")])
    assert out == [], out

    # promo: own row gets promo badge + own date; promo on a REAL row never bumps its date
    out = merge([], [mail("8", "Indeed", "Dev", "promo", "2026-10-06")])
    assert out[0]["status"] == "promo" and out[0]["last_contact"] == "2026-10-06", out
    out = merge([{"company": "indeed", "role": "Dev", "status": "applied",
                  "last_contact": "2026-10-01", "email": ""}],
                [mail("9", "Indeed", "Dev", "promo", "2026-10-06")])
    assert out[0]["status"] == "applied", out               # real status kept
    assert out[0]["last_contact"] == "2026-10-01", out      # date NOT reset by promo

    # inbox order: newest last_contact first, no-date rows last
    out = merge([{"company": "Empty", "role": "", "status": "",
                  "last_contact": "", "email": ""}],
                [mail("10", "Old Co", "Dev", "applied", "2026-09-01"),
                 mail("11", "New Co", "Dev", "applied", "2026-10-20")])
    assert [r["company"] for r in out] == ["New Co", "Old Co", "Empty"], out

    # contact = correspondent: a sent mail overwrites the row's own address
    # with the recipient (to:), never leaving the user's address behind -
    # including multi-recipient To: headers (py3.13+ strict parseaddr returns "")
    sent = EmailRecord("14", "me@gmail.com", "s", "2026-10-09", "b",
                       to_addr="hr@acme.com, talent@acme.com", direction="sent",
                       label="applied", company="Acme", role="Dev")
    out = merge([{"company": "Acme", "role": "Dev", "status": "applied",
                  "last_contact": "2026-10-08", "email": "me@gmail.com"}],
                [mail("13", "Acme", "Dev", "followup", "2026-10-08"), sent])
    assert out[0]["email"] == "hr@acme.com", out
    assert out[0]["dir"] == "sent"         # last spoke = the sent follow-up
    # old CSV rows (no dir/email keys) must not crash and default to blank
    out = merge([{"company": "Old", "role": "", "status": "applied",
                  "last_contact": "2026-10-01", "email": ""}], [])
    assert out[0]["dir"] == "" and out[0]["email"] == "", out
    # promo-only row: dir backfilled from the record that set last_contact
    out = merge([{"company": "Fresh", "role": "", "status": "promo",
                  "last_contact": "2026-10-06", "email": "a@b.c"}],
                [mail("15", "Fresh", None, "promo", "2026-10-06")])
    assert out[0]["dir"] == "inbox" and out[0]["last_contact"] == "2026-10-06", out
    print("OK: merge (advance, never-downgrade, skip, promo, noise-skip, inbox-order, contact, dir) passed")


if __name__ == "__main__":
    _self_check()
