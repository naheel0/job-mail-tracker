"""Interfaces services depend on. Adapters implement them — swap by editing one file."""
from __future__ import annotations

from typing import Protocol

from core.models import EmailRecord


class Classifier(Protocol):
    def classify(self, record: EmailRecord) -> EmailRecord:
        """Return the record with label/company/role filled in."""
        ...


class Store(Protocol):
    def save(self, records: list[EmailRecord]) -> None:
        """Persist records (CSV now, SQLite later)."""
        ...
