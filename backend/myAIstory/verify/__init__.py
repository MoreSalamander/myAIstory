"""The deterministic gates (SPEC §1–3, CONSTITUTION "Verify").

HARD RULE (ARCHITECTURE.md): this package imports no LLM client and no network
code. A verifier that calls a model is a contradiction in terms — the grader
cannot be the thing it grades.

v1 ships the blocking gates: seed_validate, bible_verify, and the three episode
gates (continuity, structure, speaker). The non-blocking phase-2 cue_verify is
not implemented yet; the schema fields it needs already exist.
"""

from myAIstory.verify.bible import verify_bible
from myAIstory.verify.continuity import verify_continuity
from myAIstory.verify.result import VerifyResult, Violation
from myAIstory.verify.seed import verify_seed
from myAIstory.verify.speaker import verify_speaker
from myAIstory.verify.structure import verify_structure

__all__ = [
    "VerifyResult",
    "Violation",
    "verify_bible",
    "verify_continuity",
    "verify_seed",
    "verify_speaker",
    "verify_structure",
]
