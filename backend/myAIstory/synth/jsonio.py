"""Extract a JSON object from a model completion.

Models wrap JSON in prose or ```json fences. This pulls out the first balanced
top-level object. A parse failure is not an exception the pipeline should crash
on — it is a verification failure (the model didn't follow instructions), so the
caller turns a JSONExtractError into a violation and retries.
"""

from __future__ import annotations

import json


class JSONExtractError(ValueError):
    pass


def extract_json(text: str) -> dict:
    """Return the first balanced JSON object found in `text`."""
    s = text.strip()

    # Strip a leading ```json / ``` fence if present.
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        if s.endswith("```"):
            s = s[: -3]

    start = s.find("{")
    if start == -1:
        raise JSONExtractError("no JSON object found in completion")

    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blob = s[start : i + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError as exc:
                    raise JSONExtractError(f"malformed JSON object: {exc}") from exc
    raise JSONExtractError("unbalanced JSON object in completion")
