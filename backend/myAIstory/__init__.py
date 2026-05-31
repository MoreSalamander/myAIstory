"""my-AI-story — a MoreSalamander StudioLabs production.

A long, multi-episode story generator with multi-voice TTS, built under the
Deterministic Scaffold thesis: human-owned constraints, AI-powered
synthesis, deterministic verification at every boundary.

This package is the backend. Phase 1 ships two sub-packages only:
  - schemas/  the typed data contracts (SeriesSeed, Bible, Episode, VoiceMap)
  - verify/   the pure-Python gates (NO LLM, NO network) that decide whether
              a model proposal is allowed to exist.
"""

__version__ = "0.1.0"
