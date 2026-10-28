"""Issue 5 adapter: tracker.csv <-> rows. The only file that knows CSV exists.

Run:  python adapters/csv_store.py    (save/load roundtrip self-check)
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root

from core.models import FIELDS

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "tracker.csv"


def load(path: Path = DEFAULT_PATH) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def save(rows: list[dict], path: Path = DEFAULT_PATH) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, restval="")
        writer.writeheader()
        writer.writerows(rows)


def _self_check() -> None:
    tmp = Path("._tracker_test.csv")
    rows = [{"company": "Acme", "role": "Dev", "status": "applied",
             "last_contact": "2026-10-01"}]
    try:
        save(rows, tmp)
        back = load(tmp)
        assert back == rows, f"roundtrip broke: {back}"
        assert load(Path("._does_not_exist.csv")) == []  # missing file -> empty
    finally:
        tmp.unlink(missing_ok=True)
    print("OK: csv roundtrip + missing-file handling passed")


if __name__ == "__main__":
    _self_check()
