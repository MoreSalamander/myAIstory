"""Pluggable local text-to-speech (ARCHITECTURE.md `tts/`).

Everything that renders audio implements the `TTSEngine` protocol. The pipeline
depends only on that protocol, so the backend swaps freely: ScriptedTTS for
tests/offline runs, PiperTTS for real local synthesis, and (later) other local
engines behind the same seam. `stitch` assembles per-line clips into one
episode track without caring which backend produced them.
"""

from myAIstory.tts.base import Clip, TTSEngine, Voice
from myAIstory.tts.kokoro import KokoroError, KokoroTTS
from myAIstory.tts.piper import PiperError, PiperTTS
from myAIstory.tts.scripted import ScriptedTTS
from myAIstory.tts.stitch import DEFAULT_GAP_MS, silence, stitch

__all__ = [
    "Clip",
    "TTSEngine",
    "Voice",
    "ScriptedTTS",
    "PiperTTS",
    "PiperError",
    "KokoroTTS",
    "KokoroError",
    "stitch",
    "silence",
    "DEFAULT_GAP_MS",
]
