"""Issue 2: .eml file -> EmailRecord. Stdlib only, never crashes on bad mail.

Run:  python adapters/eml_parser.py            (self-check, no emails needed)
      python adapters/eml_parser.py inbox       (parse real files)
"""
from __future__ import annotations

import hashlib
import re
import sys
from datetime import timezone
from email import message_from_file
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, so `python adapters/...` works

from core.models import EmailRecord

BODY_LIMIT = 1000  # ponytail: hard truncate; models don't need thread history
_TAG_RE = re.compile(r"<[^>]+>\s*")


def _html_to_text(html: str) -> str:
    return _TAG_RE.sub(" ", html)


def _plain_body(msg: Message) -> str:
    plain, html = [], []
    for part in msg.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            continue
        try:
            text = payload.decode(part.get_content_charset() or "utf-8")
        except (LookupError, UnicodeDecodeError):
            text = payload.decode("utf-8", errors="replace")
        if not text:
            continue
        (plain if part.get_content_type() == "text/plain" else html).append(text)
    body = "\n".join(plain) or _html_to_text("\n".join(html))
    return body.strip()[:BODY_LIMIT]


def _date_iso(msg: Message) -> str:
    """Always UTC ISO 8601: string order must equal time order for 'newest wins'.
    Unparsable date -> '' (the email is kept; a raw garbage date breaks the UI)."""
    try:
        dt = parsedate_to_datetime(msg.get("Date", ""))
    except (ValueError, TypeError):
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # email spec: no offset = UTC
    return dt.astimezone(timezone.utc).isoformat()


def parse_file(path: Path) -> EmailRecord:
    with path.open(encoding="utf-8", errors="replace") as f:
        msg = message_from_file(f)
    message_id = msg.get("Message-ID") or f"{msg.get('From')}|{msg.get('Date')}|{msg.get('Subject')}"
    # decode RFC 2047 encoded words (=?UTF-8?B?...?=) so the model reads real text
    decode = lambda h: str(make_header(decode_header(h or "")))
    return EmailRecord(
        id=hashlib.sha256(message_id.encode()).hexdigest()[:16],
        from_addr=decode(msg.get("From")),
        subject=decode(msg.get("Subject")),
        date=_date_iso(msg),
        body=_plain_body(msg),
    )


def parse_dir(folder: Path) -> list[EmailRecord]:
    """Parse every *.eml in folder. Bad files are logged and skipped, batch continues."""
    records, seen = [], set()
    for path in sorted(folder.glob("*.eml")):
        try:
            rec = parse_file(path)
        except Exception as exc:  # ponytail: one corrupt export must not kill the batch
            print(f"  skip {path.name}: {exc}", file=sys.stderr)
            continue
        if rec.id not in seen:
            seen.add(rec.id)
            records.append(rec)
    return records


def _self_check() -> None:
    sample = """From: Jane Recruiter <jane@acme.com>
To: me@mail.com
Subject: Interview invite - Backend Developer
Date: Tue, 27 Oct 2026 09:30:00 +0000
Message-ID: <abc-123@acme.com>
Content-Type: text/plain; charset=utf-8

Hi! We would like to schedule an interview.
"""
    p = Path("._sample.eml")
    p.write_text(sample, encoding="utf-8")
    try:
        rec = parse_file(p)
        assert rec.subject == "Interview invite - Backend Developer", rec.subject
        assert "schedule an interview" in rec.body
        assert rec.date.startswith("2026-10-27"), rec.date
        assert len(rec.id) == 16
        assert parse_dir(Path("."))  # sample file picked up from dir
    finally:
        p.unlink()
    print("OK: parser self-check passed")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for r in parse_dir(Path(sys.argv[1])):
            print(f"{r.date} | {r.from_addr} | {r.subject}")
    else:
        _self_check()
