"""Issue 5 adapter: tracker.csv <-> rows. The only file that knows CSV exists.

Run:  python adapters/csv_store.py    (save/load roundtrip self-check)
"""
from __future__ import annotations

import csv
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root

from core.models import FIELDS

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "tracker.csv"


def load(path: Path = DEFAULT_PATH) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not set(FIELDS) <= set(reader.fieldnames):
            print(f"WARNING: {path.name} has wrong columns ({reader.fieldnames}) - "
                  "ignoring it, tracker rebuilds from .state.json", file=sys.stderr)
            return []
        return list(reader)


def atomic_write(path: Path, text: str) -> None:
    """Write via temp file + rename: a crash mid-write can't leave a truncated file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)  # atomic on Windows


def save(rows: list[dict], path: Path = DEFAULT_PATH) -> None:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS, restval="")
    writer.writeheader()
    writer.writerows(rows)
    atomic_write(path, buf.getvalue())


def _self_check() -> None:
    tmp = Path("._tracker_test.csv")
    rows = [{"company": "Acme", "role": "Dev", "email": "jane@acme.com",
             "status": "applied", "last_contact": "2026-10-01"}]
    try:
        save(rows, tmp)
        back = load(tmp)
        assert back == rows, f"roundtrip broke: {back}"
        assert load(Path("._does_not_exist.csv")) == []  # missing file -> empty
        tmp.write_text("company,role\nAcme,Dev\n", encoding="utf-8")  # wrong columns
        assert load(tmp) == [], "corrupt CSV must be ignored, not crash"
    finally:
        tmp.unlink(missing_ok=True)
    print("OK: csv roundtrip + missing-file + wrong-columns handling passed")


if __name__ == "__main__":
    _self_check()
