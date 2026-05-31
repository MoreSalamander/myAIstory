"""The verdict type every gate returns.

A verifier NEVER raises on bad input — it returns a VerifyResult. That is the
whole point of the deterministic scaffold: the model's proposal is data, the
verifier is a function that decides whether the data is allowed through, and a
rejection must carry a machine-readable reason so the pipeline can feed the
specific violation back into a bounded retry (ARCHITECTURE.md, CONSTITUTION.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

_M = TypeVar("_M", bound="BaseModel")


@dataclass(frozen=True)
class Violation:
    """A single reason a proposal was rejected."""

    code: str               # stable, machine-readable, e.g. "duplicate_name"
    message: str            # human-readable explanation
    field: Optional[str] = None  # dotted path to the offending field, if any

    def __str__(self) -> str:
        loc = f" [{self.field}]" if self.field else ""
        return f"{self.code}{loc}: {self.message}"


@dataclass
class VerifyResult:
    """The outcome of one gate."""

    gate: str                                   # e.g. "continuity_verify"
    checks: list[str] = field(default_factory=list)       # checks attempted
    violations: list[Violation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.violations

    def add_check(self, name: str) -> None:
        if name not in self.checks:
            self.checks.append(name)

    def fail(self, code: str, message: str, field: Optional[str] = None) -> None:
        self.violations.append(Violation(code=code, message=message, field=field))

    def __bool__(self) -> bool:
        return self.passed

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        head = f"[{status}] {self.gate} (checks: {', '.join(self.checks) or 'none'})"
        if self.passed:
            return head
        body = "\n".join(f"  - {v}" for v in self.violations)
        return f"{head}\n{body}"


def violations_from_pydantic(exc: ValidationError) -> list[Violation]:
    """Translate a Pydantic ValidationError into structured violations.

    This lets a malformed proposal be reported the same way as a semantic
    failure, instead of crashing the pipeline.
    """
    out: list[Violation] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        out.append(
            Violation(
                code=f"schema.{err.get('type', 'invalid')}",
                message=err.get("msg", "schema validation failed"),
                field=loc or None,
            )
        )
    return out


def parse(model_cls: Type[_M], raw: object) -> tuple[Optional[_M], list[Violation]]:
    """Try to build a typed model from a raw proposal.

    Returns (model, []) on success or (None, [violations]) on a structural
    failure. Accepts an already-constructed model instance and passes it
    through, so verifiers compose cleanly whether handed a dict or an object.
    """
    if isinstance(model_cls, type) and isinstance(raw, model_cls):
        return raw, []  # already a valid instance
    try:
        return model_cls.model_validate(raw), []
    except ValidationError as exc:
        return None, violations_from_pydantic(exc)
