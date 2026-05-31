"""Ollama streaming client (stdlib only — no third-party HTTP dependency).

Implements the LLM protocol against a local Ollama server's /api/generate
endpoint, yielding tokens as they stream. Kept dependency-free on purpose: the
synthesis layer should be transparent and easy to audit.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Iterator

from myAIstory.synth.router import spec_for

DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    """Streams completions from a local Ollama server."""

    def __init__(self, host: str = DEFAULT_HOST, timeout: float = 600.0) -> None:
        self.host = host.rstrip("/")
        self.timeout = timeout

    def stream(self, *, role: str, system: str, prompt: str) -> Iterator[str]:
        spec = spec_for(role)
        payload = {
            "model": spec.model,
            "prompt": prompt,
            "system": system,
            "stream": True,
            "options": {
                "temperature": spec.temperature,
                "num_ctx": spec.num_ctx,
                "num_predict": spec.num_predict,
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if obj.get("error"):
                        raise OllamaError(obj["error"])
                    chunk = obj.get("response", "")
                    if chunk:
                        yield chunk
                    if obj.get("done"):
                        break
        except urllib.error.URLError as exc:  # pragma: no cover - network path
            raise OllamaError(
                f"could not reach Ollama at {self.host}: {exc}. "
                "Is `ollama serve` running?"
            ) from exc
