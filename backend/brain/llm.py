"""Optional Claude calls over plain HTTPS (no SDK needed). Every response is cached on disk by prompt hash,
so a demo never waits on the API twice. Without ANTHROPIC_API_KEY the caller falls back to extractive answers."""
import hashlib
import json
import os
import pathlib
import urllib.request

CACHE = pathlib.Path(__file__).resolve().parents[1] / "cache"
MODEL_ANSWER = os.environ.get("BRAIN_MODEL", "claude-sonnet-5-5")


def available():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def complete(system, user, model=None, max_tokens=700):
    model = model or MODEL_ANSWER
    key = hashlib.sha256(json.dumps([model, system, user]).encode()).hexdigest()[:24]
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"{key}.json"
    if f.exists():
        return json.loads(f.read_text())["text"]
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({"model": model, "max_tokens": max_tokens, "system": system,
                         "messages": [{"role": "user", "content": user}]}).encode(),
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    text = "".join(b.get("text", "") for b in data.get("content", []))
    f.write_text(json.dumps({"model": model, "text": text}))
    return text
