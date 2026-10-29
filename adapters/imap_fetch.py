"""Issue 11 / Phase 6: pull new mail over IMAP straight into inbox/ - any provider.

Stdlib imaplib only, no dependencies. Reads credentials from .env (never committed):

  IMAP_HOST=imap.gmail.com
  IMAP_USER=you@gmail.com
  IMAP_PASSWORD=your-app-password     # Gmail: 2FA -> Security -> App passwords

Run:  python main.py --sync [folder]
State: .sync_state holds the last sync date; files are deduped by Message-ID,
       so re-syncing never downloads the same email twice.

Self-check (no network): python adapters/imap_fetch.py
"""
from __future__ import annotations

import hashlib
import imaplib
import os
import ssl
import sys
from datetime import date, timedelta
from email import message_from_bytes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SYNC_DAYS = int(os.environ.get("IMAP_SINCE_DAYS", "30"))  # ponytail: first sync window
STATE_FILE = ROOT / ".sync_state"


def _env(name: str) -> str:
    """os.environ first, then .env file (5-line parser - no python-dotenv needed)."""
    if os.environ.get(name):
        return os.environ[name]
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():  # utf-8-sig: eats Notepad's BOM
            line = line.strip()
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def _cfg() -> tuple[str, str, str]:
    host, user, pw = _env("IMAP_HOST"), _env("IMAP_USER"), _env("IMAP_PASSWORD")
    if not all((host, user, pw)):
        raise SystemExit(
            "IMAP not configured. Create .env with:\n"
            "  IMAP_HOST=imap.gmail.com\n"
            "  IMAP_USER=you@gmail.com\n"
            "  IMAP_PASSWORD=your-app-password   (Gmail: 2FA -> App passwords)"
        )
    return host, user, pw


def _since() -> date:
    if STATE_FILE.exists():
        try:
            return date.fromisoformat(STATE_FILE.read_text(encoding="utf-8").strip()[:10])
        except ValueError:
            pass
    return date.today() - timedelta(days=SYNC_DAYS)


def _save(raw: bytes, folder: Path) -> bool:
    """Write one message as .eml, named by Message-ID hash. False = already have it."""
    msg = message_from_bytes(raw)
    key = msg.get("Message-ID") or f"{msg.get('From')}|{msg.get('Date')}|{msg.get('Subject')}"
    path = folder / (hashlib.sha256(key.encode()).hexdigest()[:24] + ".eml")
    if path.exists():
        return False
    folder.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return True


def sync(folder: Path, days: int | None = None) -> int:
    """Download emails since the last sync into folder. Returns count of new files."""
    host, user, pw = _cfg()
    since = _since()
    try:
        # default context: verify the server cert - imaplib's own default does NOT,
        # which would expose the app password to a man-in-the-middle
        imap = imaplib.IMAP4_SSL(host, ssl_context=ssl.create_default_context())
    except OSError as exc:
        raise SystemExit(f"Cannot reach IMAP server {host} ({exc}).\n"
                         f"Fix: check the host name and your network connection.") from exc
    try:
        try:
            imap.login(user, pw)
        except imaplib.IMAP4.error as exc:
            raise SystemExit(
                f"Gmail rejected the login ({exc}). Checklist:\n"
                "  1. IMAP_USER = your full real Gmail address (not the ... placeholder)\n"
                "  2. 2-Step Verification must be ON (myaccount.google.com/security)\n"
                "  3. IMAP_PASSWORD = a 16-char APP password, not your account password\n"
                "     (Google account -> search 'App passwords' -> create one)\n"
                "  4. spaces in the app password are fine, quotes optional"
            ) from exc
        imap.select("INBOX")
        typ, found = imap.search(None, "SINCE", since.strftime("%d-%b-%Y"))
        if typ != "OK":  # otherwise we'd write today's date and silently skip these forever
            raise SystemExit(f"IMAP search failed ({found}) - not advancing sync state, retry later.")
        new = 0
        for num in found[0].split():
            _, data = imap.fetch(num, "(RFC822)")
            if data and isinstance(data[0], tuple) and _save(data[0][1], folder):
                new += 1
    finally:
        imap.logout()
    STATE_FILE.write_text(date.today().isoformat(), encoding="utf-8")
    return new


def _self_check() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        raw = (b"From: a@b.c\r\nSubject: T\r\nMessage-ID: <dup@x>\r\nDate: Mon, 19 Oct 2026 "
               b"10:00:00 +0000\r\n\r\nbody")
        assert _save(raw, folder) is True, "first save should write"
        assert _save(raw, folder) is False, "same Message-ID must dedup"
        assert len(list(folder.glob('*.eml'))) == 1

    # missing config: temporarily point ROOT at an empty dir so the real .env is ignored
    global ROOT
    saved_root, ROOT = ROOT, Path(tempfile.mkdtemp())
    try:
        try:
            _cfg()
            raise AssertionError("missing config should SystemExit")
        except AssertionError:
            raise
        except SystemExit as exc:
            assert "IMAP not configured" in str(exc), exc
    finally:
        ROOT = saved_root
    print("OK: imap fetch (save, dedup-by-Message-ID, config error) passed")


if __name__ == "__main__":
    _self_check()
