"""Kokoro — a higher-fidelity local TTS backend (CONSTITUTION: local-only).

Kokoro-82M (https://github.com/hexgrad/kokoro) is an open-weight, 82M-parameter
neural TTS that sounds markedly more natural and expressive than Piper while
staying entirely offline. This adapter runs the ONNX build (`kokoro-onnx`) so no
PyTorch is needed at runtime: it loads the model + voice pack once and renders
one line at a time.

Like PiperTTS this is a thin adapter implementing the same `TTSEngine` protocol,
so the pipeline cannot tell the backends apart — `voice_assign` casts onto
whatever voices the backend reports, and `stitch` concatenates the clips it
returns. Kokoro emits float32 samples at 24 kHz; `synth` converts those to the
same signed-16-bit mono PCM `Clip` every other backend produces, so downstream
stitching/mixing is unchanged.

A model directory holds two files (downloaded once from the kokoro-onnx
release):

    <model_dir>/kokoro-v1.0.onnx     the model weights
    <model_dir>/voices-v1.0.bin      the bundled voice embeddings

Nothing here is exercised until those files (and the `kokoro-onnx` package) are
present; until then ScriptedTTS covers the audio path in tests — exactly the
swap-the-backend discipline PiperTTS follows.
"""

from __future__ import annotations

from pathlib import Path

from myAIstory.tts.base import Clip, Voice

KOKORO_SAMPLE_RATE = 24000  # Kokoro renders at 24 kHz


class KokoroError(RuntimeError):
    pass


class KokoroTTS:
    """Render lines with the local Kokoro-82M ONNX model.

    `model_dir` holds `kokoro-v1.0.onnx` + `voices-v1.0.bin`. `voices()` reports
    Kokoro's built-in named voices (e.g. `af_heart`, `am_michael`, `bf_emma`),
    so `voice_assign`'s deterministic casting maps characters onto them with no
    extra config. `speed` scales delivery globally (1.0 = natural); the spoken
    language is inferred per voice (the `b*` voices are British English).
    """

    def __init__(
        self,
        model_dir: str | Path,
        *,
        model_file: str = "kokoro-v1.0.onnx",
        voices_file: str = "voices-v1.0.bin",
        speed: float = 1.0,
        voices: list[str] | None = None,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.model_path = self.model_dir / model_file
        self.voices_path = self.model_dir / voices_file
        self.speed = speed

        if not self.model_path.exists() or not self.voices_path.exists():
            raise KokoroError(
                "kokoro model files not found — expected "
                f"{self.model_path} and {self.voices_path}"
            )

        try:
            from kokoro_onnx import Kokoro  # lazy: only needed for real synthesis
        except ImportError as exc:  # pragma: no cover - depends on optional dep
            raise KokoroError(
                "kokoro-onnx is not installed (pip install kokoro-onnx)"
            ) from exc

        try:
            self._kokoro = Kokoro(str(self.model_path), str(self.voices_path))
        except Exception as exc:  # pragma: no cover - model load failure
            raise KokoroError(f"failed to load kokoro model: {exc}") from exc

        discovered = self._discover_voices()
        self._voice_ids: list[str] = list(voices) if voices else discovered
        if not self._voice_ids:
            raise KokoroError("kokoro reported no voices")

    def _discover_voices(self) -> list[str]:
        """The model's built-in voice names, sorted for stable casting."""
        getter = getattr(self._kokoro, "get_voices", None)
        try:
            names = list(getter()) if callable(getter) else []
        except Exception:  # pragma: no cover - defensive
            names = []
        return sorted(str(n) for n in names)

    @staticmethod
    def _lang_for(voice: str) -> str:
        """Kokoro voice ids are language-prefixed: `b*` = British English."""
        return "en-gb" if voice[:1].lower() == "b" else "en-us"

    def voices(self) -> list[Voice]:
        return [
            Voice(id=vid, label=vid.replace("_", " ").title())
            for vid in self._voice_ids
        ]

    def synth(self, *, text: str, voice: str) -> Clip:
        if voice not in self._voice_ids:
            # Be defensive: the voice map should always resolve, but fall back to
            # the first voice rather than crash mid-episode.
            voice = self._voice_ids[0]

        if not (text or "").strip():
            return Clip(frames=b"", sample_rate=KOKORO_SAMPLE_RATE)

        try:
            import numpy as np

            samples, sample_rate = self._kokoro.create(
                text, voice=voice, speed=self.speed, lang=self._lang_for(voice)
            )
        except Exception as exc:  # pragma: no cover - runtime synth failure
            raise KokoroError(f"kokoro failed for voice {voice!r}: {exc}") from exc

        # Kokoro yields float32 in [-1, 1]; pack to little-endian signed 16-bit
        # PCM, the format every Clip carries.
        pcm = np.clip(np.asarray(samples, dtype="float32"), -1.0, 1.0)
        frames = (pcm * 32767.0).astype("<i2").tobytes()
        return Clip(frames=frames, sample_rate=int(sample_rate))
