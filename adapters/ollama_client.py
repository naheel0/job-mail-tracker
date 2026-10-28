"""Issue 3: classify one email with a local Ollama model. Stdlib HTTP, no SDK.

Run:  python adapters/ollama_client.py          (self-check — needs ollama running)
Env:  OLLAMA_MODEL (default llama3.2), OLLAMA_HOST (default http://localhost:11434)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root

from core.models import LABELS, EmailRecord

MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")  # exact tag: bare 'llama3.2' 404s if only :3b pulled
HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "180"))  # first run loads a 2GB model into RAM
PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "classify.txt").read_text(encoding="utf-8")


def _generate(prompt: str) -> dict:
    body = json.dumps({"model": MODEL, "prompt": prompt, "stream": False, "format": "json"}).encode()
    req = urllib.request.Request(f"{HOST}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(json.loads(resp.read().decode())["response"])
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"Cannot reach Ollama at {HOST} ({exc.reason}).\n"
            f"Fix: run `ollama serve`, then `ollama pull {MODEL}`"
        ) from exc
    except TimeoutError as exc:
        raise SystemExit(
            f"Ollama did not answer in {TIMEOUT}s (first run loads the model).\n"
            f"Fix: retry, or raise OLLAMA_TIMEOUT={TIMEOUT * 2}"
        ) from exc


def classify(record: EmailRecord) -> EmailRecord:
    """Fills label/company/role. Bad model output: retry once, then fall back to 'noise'."""
    answer: dict = {}
    for _ in range(2):  # ponytail: format:'json' already guarantees JSON; this catches wrong shape
        answer = _generate(PROMPT.format(sender=record.from_addr, subject=record.subject,
                                         date=record.date, body=record.body))
        if isinstance(answer, dict) and answer.get("label") in LABELS:
            break
    record.label = answer.get("label") if answer.get("label") in LABELS else "noise"
    record.company = (answer.get("company") or None) if isinstance(answer, dict) else None
    record.role = (answer.get("role") or None) if isinstance(answer, dict) else None
    return record


class OllamaClassifier:
    """ports.Classifier implementation — what main.py wires in."""

    def classify(self, record: EmailRecord) -> EmailRecord:
        return classify(record)


def _self_check() -> None:
    sample = EmailRecord(id="chk", from_addr="jane@acme.com",
                         subject="Interview invite - Backend Developer",
                         date="2026-10-27T09:30:00+00:00",
                         body="Hi! We would like to schedule an interview for the backend role.")
    result = classify(sample)
    assert result.label in LABELS, result.label
    print(f"OK: label={result.label} company={result.company} role={result.role}")


if __name__ == "__main__":
    _self_check()
