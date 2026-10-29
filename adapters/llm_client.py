"""Issue 3: classify one email through ANY OpenAI-compatible chat API. Stdlib HTTP, no SDK.

Works with local endpoints (Ollama /v1, LM Studio, llama.cpp server, vLLM) and cloud
providers (Groq, Together, OpenRouter, DeepSeek, OpenAI) - they all speak /chat/completions.

Run:  python adapters/llm_client.py       (self-check — needs an endpoint running)
Env:  LLM_BASE_URL (default http://localhost:11434/v1 = local Ollama)
      LLM_MODEL    (default llama3.2:3b — exact tag for Ollama, provider's name for cloud)
      LLM_API_KEY  (optional — only needed by cloud providers)
      LLM_TIMEOUT  (default 180)
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

BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "llama3.2:3b")  # exact tag: bare 'llama3.2' 404s if only :3b pulled
API_KEY = os.environ.get("LLM_API_KEY", "")          # empty = local endpoint, no auth
TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "180"))  # first run loads a 2GB model into RAM
PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "classify.txt").read_text(encoding="utf-8")
SYSTEM = "You are an email classifier. Reply with ONLY one JSON object - no prose, no code fences."

def _generate(user_text: str) -> dict:
    body = json.dumps({"model": MODEL, "messages": [{"role": "system", "content": SYSTEM},
                                                    {"role": "user", "content": user_text}],
                       "stream": False, "temperature": 0}).encode()
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    req = urllib.request.Request(f"{BASE_URL}/chat/completions", data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            content = json.loads(resp.read().decode())["choices"][0]["message"]["content"]
        return _extract_json(content)
    except urllib.error.HTTPError as exc:  # provider answered with an error (bad key, bad model...)
        raise SystemExit(
            f"LLM at {BASE_URL} rejected the request: HTTP {exc.code} {exc.reason}.\n"
            f"Fix: check LLM_MODEL matches the provider (`ollama list` / provider's model list"
            f"{' and LLM_API_KEY is valid' if API_KEY else ''})"
        ) from exc
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"Cannot reach LLM at {BASE_URL} ({exc.reason}).\n"
            f"Fix: for local Ollama run `ollama serve`, then `ollama pull {MODEL}`;"
            f" or point LLM_BASE_URL at another OpenAI-compatible endpoint"
            f"{' and set LLM_API_KEY' if not API_KEY else ''}"
        ) from exc
    except TimeoutError as exc:
        raise SystemExit(
            f"LLM did not answer in {TIMEOUT}s (first run loads the model).\n"
            f"Fix: retry, or raise LLM_TIMEOUT={TIMEOUT * 2}"
        ) from exc
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:  # answered but garbage
        raise SystemExit(
            f"LLM at {BASE_URL} answered but not with usable JSON ({exc}).\n"
            f"Fix: retry the run; if it persists, try another LLM_MODEL."
        ) from exc


def _extract_json(text: str) -> dict:
    """Tolerate markdown fences / surrounding prose - cloud models love those."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    fenced = text[text.find("{") : text.rfind("}") + 1]  # strip ```json ... ``` and chit-chat
    return json.loads(fenced)  # let the caller's JSON error handler report failures


_EMPTY = {"", "null", "none", "n/a", "na", "-", "unknown"}


def _clean(value) -> str | None:
    """Models answer 'null' as a string - that must never become a company name."""
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    return None if v in _EMPTY else v


def classify(record: EmailRecord) -> EmailRecord:
    """Fills label/company/role. Bad model output: retry once, then fall back to 'noise'."""
    hint = ""
    answer: dict = {}
    for _ in range(2):  # providers guarantee JSON-ish text, not shape - we check shape here
        answer = _generate(PROMPT.format(direction=record.direction, sender=record.from_addr,
                                         to=record.to_addr, subject=record.subject,
                                         date=record.date, body=record.body) + hint)
        if _label_of(answer):
            break
        hint = ('\nAnswer ONLY a JSON object like {"label":"applied","company":null,'
                '"role":null} where label is one of: ' + ", ".join(LABELS))
    record.label = _label_of(answer) or "noise"
    if isinstance(answer, dict):  # a bare string/array answer must not crash the loop
        record.company = _clean(answer.get("company"))
        record.role = _clean(answer.get("role"))
    else:
        record.company = record.role = None
    return record


def _label_of(answer) -> str | None:
    """Accept the label case-insensitively; non-dict answers -> None (caller falls back)."""
    label = answer.get("label") if isinstance(answer, dict) else None
    if isinstance(label, str) and label.strip().lower() in LABELS:
        return label.strip().lower()
    return None


class LLMClassifier:
    """ports.Classifier implementation — what main.py wires in."""

    def classify(self, record: EmailRecord) -> EmailRecord:
        return classify(record)


def _self_check() -> None:
    assert _clean("null") is None and _clean("  N/A ") is None and _clean(None) is None
    assert _clean("Acme Corp") == "acme corp", _clean("Acme Corp")  # junk guard first, no model needed
    assert _extract_json('{"a":1}') == {"a": 1}
    assert _extract_json('```json\n{"a":1}\n```') == {"a": 1}   # fenced
    assert _extract_json('Sure! {"a":1} hope that helps') == {"a": 1}  # prose around it
    sample = EmailRecord(id="chk", from_addr="jane@acme.com",
                         subject="Interview invite - Backend Developer",
                         date="2026-10-27T09:30:00+00:00",
                         body="Hi! We would like to schedule an interview for the backend role.")
    result = classify(sample)
    assert result.label in LABELS, result.label
    print(f"OK: label={result.label} company={result.company} role={result.role} (via {BASE_URL}, {MODEL})")


if __name__ == "__main__":
    _self_check()
