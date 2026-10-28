"""Issue 4: batch classification. One bad email must never kill the batch.

Pure logic — no I/O here (design rule: services talk through protocols only).
Run:  python services/classify.py     (self-check with a fake classifier, no Ollama needed)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root

from core.models import EmailRecord, LABELS
from core.ports import Classifier


def classify_all(records: list[EmailRecord], classifier: Classifier) -> list[EmailRecord]:
    """Classify each record, dedup by id. Failures are reported and skipped."""
    out, seen, failed = [], set(), []
    for rec in records:
        if rec.id in seen:
            continue
        seen.add(rec.id)
        try:
            out.append(classifier.classify(rec))
        except Exception as exc:  # ponytail: 1 broken email != 0 results
            failed.append((rec.subject or rec.id, exc))
    for subject, exc in failed:
        print(f"  classify failed: {subject[:50]!r}: {exc}", file=sys.stderr)
    return out


class _FakeClassifier:
    """Deterministic stand-in for Ollama — lets services be tested offline."""

    def classify(self, record: EmailRecord) -> EmailRecord:
        record.label = "interview" if "interview" in record.subject.lower() else "noise"
        record.company = "acme"
        return record


def _self_check() -> None:
    mails = [
        EmailRecord("1", "a@x.com", "Interview invite", "2026-10-27", "hi"),
        EmailRecord("2", "b@x.com", "Interview invite", "2026-10-27", "hi"),  # dup id? no - dup below
        EmailRecord("1", "a@x.com", "Interview invite", "2026-10-27", "hi"),  # duplicate id
        EmailRecord("3", "c@x.com", "Newsletter", "2026-10-27", "hi"),
    ]
    out = classify_all(mails, _FakeClassifier())
    assert len(out) == 3, f"dedup failed: {len(out)}"  # ids 1,2,3 (duplicate 1 dropped)
    assert [r.label for r in out] == ["interview", "interview", "noise"]
    assert all(r.label in LABELS for r in out)

    class _Boom:
        def classify(self, record):
            raise RuntimeError("model exploded")

    out2 = classify_all(mails[:2], _Boom())
    assert out2 == []  # all failed -> empty list, no exception
    print("OK: classify_all batch + dedup + failure isolation passed")


if __name__ == "__main__":
    _self_check()
