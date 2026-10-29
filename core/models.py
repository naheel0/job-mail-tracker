"""Shared contract: every pipeline stage speaks EmailRecord.

Stage rule: data in, data out — nothing else crosses a stage boundary.
"""
from __future__ import annotations

from dataclasses import dataclass

LABELS = ("applied", "recruiter", "interview", "rejected", "offer", "followup", "promo", "noise")

# tracker.csv columns — shared by track service and csv adapter
FIELDS = ("company", "role", "email", "status", "last_contact")


@dataclass
class EmailRecord:
    id: str                 # hash of Message-ID — dedup key
    from_addr: str
    subject: str
    date: str               # ISO 8601
    body: str               # plain text, truncated
    label: str = ""         # one of LABELS (filled by classify)
    company: str | None = None
    role: str | None = None
    status: str | None = None   # applied -> interviewing -> rejected | offer
