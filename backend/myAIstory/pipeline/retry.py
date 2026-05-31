"""Bounded-retry-then-skip (CONSTITUTION.md, ARCHITECTURE.md).

The load-bearing control flow of the whole studio thesis: draft → gate → on
failure, re-prompt with the *specific* violations a bounded number of times →
on exhaustion, skip and log. Nothing failing is ever forced through.

`run_with_retry` is gate-agnostic: it takes a `produce` callable (returns raw
model text given optional feedback) and a list of gate callables (obj ->
VerifyResult). It owns the parse step, the event emissions, and the budget.
"""

from __future__ import annotations

from typing import Callable, Optional

from myAIstory.events import EventEmitter
from myAIstory.synth.jsonio import JSONExtractError, extract_json
from myAIstory.verify.result import VerifyResult

Produce = Callable[[Optional[list[str]]], str]
Gate = Callable[[dict], VerifyResult]


def run_with_retry(
    produce: Produce,
    gates: list[Gate],
    emit: EventEmitter,
    *,
    stage: str,
    max_retries: int = 2,
) -> tuple[Optional[dict], list[VerifyResult]]:
    """Draft-and-gate with bounded retries.

    Returns (obj, results) on success, or (None, results) if the retry budget is
    exhausted. Total attempts = max_retries + 1.
    """
    feedback: Optional[list[str]] = None
    last_results: list[VerifyResult] = []

    for attempt in range(1, max_retries + 2):
        text = produce(feedback)

        # Parse: a non-JSON completion is a verification failure, not a crash.
        try:
            obj = extract_json(text)
        except JSONExtractError as exc:
            violations = [f"json_parse: {exc}"]
            last_results = []
        else:
            last_results = [gate(obj) for gate in gates]
            violations = [str(v) for r in last_results for v in r.violations]
            if not violations:
                for r in last_results:
                    emit.verify_pass(r.gate, r.checks)
                return obj, last_results

        emit.verify_fail(stage, violations, attempt)

        if attempt <= max_retries:
            emit.retry(stage, attempt + 1, reason=f"{len(violations)} violation(s)")
            feedback = violations
        else:
            emit.skip(stage, reason=f"retry budget exhausted after {attempt} attempts")

    return None, last_results
