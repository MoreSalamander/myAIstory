"""Voice cloning — match a short reference clip (CONSTITUTION: local-only).

Where Piper and Kokoro speak in fixed, built-in timbres, a cloning model takes
a *reference clip* you supply (~6-15s of clean speech) and renders new lines in
that voice. So to cast a deep, sexy narrator you just drop a sample of that
voice into the references directory — the model matches its timbre. This adapter
wraps Coqui's XTTS-v2 (`tts_models/multilingual/multi-dataset/xtts_v2`), the
most ergonomic local clone-from-a-single-clip model; the same seam could host
F5-TTS later by swapping the `model` id and the synth call.

Like the other backends this is a thin adapter implementing the `TTSEngine`
protocol, so the pipeline cannot tell it apart: each reference file is a
castable "voice" (id = file stem), `voice_assign` maps characters onto whatever
references you provide, and `stitch` concatenates the clips. XTTS emits float32
samples; `synth` packs those into the same signed-16-bit mono PCM `Clip` every
backend produces.

A references directory holds one audio file per voice::

    <references_dir>/narrator.wav     a ~6-15s clean sample of the target voice
    <references_dir>/ember.flac       (any of .wav/.flac/.mp3/.ogg)

Nothing here runs until both the reference clips and the `TTS` package are
present (the XTTS model itself is fetched once into Coqui's cache on first use);
until then ScriptedTTS covers the audio path in tests — the same
swap-the-backend discipline PiperTTS and KokoroTTS follow.
"""

from __future__ import annotations

from pathlib import Path

from myAIstory.tts.base import Clip, Voice

CLONE_SAMPLE_RATE = 24000  # XTTS-v2 renders at 24 kHz
DEFAULT_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"
REFERENCE_EXTS = (".wav", ".flac", ".mp3", ".ogg")


class CloneError(RuntimeError):
    pass


class CloneTTS:
    """Render lines by cloning short reference clips with XTTS-v2.

    `references_dir` holds one audio file per voice (`<id>.wav`, ~6-15s of clean
    speech); the voice `id` is the file stem, so deterministic casting maps
    characters onto whatever references you drop in. `language` is the synthesis
    language XTTS speaks (default English); `speed` scales delivery globally
    (1.0 = natural). The heavy `TTS` model is loaded lazily so the package stays
    importable without the optional dependency.
    """

    def __init__(
        self,
        references_dir: str | Path,
        *,
        model: str = DEFAULT_MODEL,
        language: str = "en",
        speed: float = 1.0,
        use_gpu: bool = False,
        voices: list[str] | None = None,
    ) -> None:
        self.references_dir = Path(references_dir)
        self.model = model
        self.language = language
        self.speed = speed
        self._refs: dict[str, Path] = {}
        self._discover(voices)

        try:
            from TTS.api import TTS  # lazy: only needed for real synthesis
        except ImportError as exc:  # pragma: no cover - depends on optional dep
            raise CloneError(
                "coqui TTS is not installed (pip install coqui-tts)"
            ) from exc

        try:
            self._tts = TTS(self.model, progress_bar=False, gpu=use_gpu)
        except Exception as exc:  # pragma: no cover - model load failure
            raise CloneError(f"failed to load clone model {self.model!r}: {exc}") from exc

    def _discover(self, voices: list[str] | None) -> None:
        if not self.references_dir.is_dir():
            raise CloneError(f"clone references dir not found: {self.references_dir}")
        for ref in sorted(self.references_dir.iterdir()):
            if ref.suffix.lower() in REFERENCE_EXTS:
                self._refs[ref.stem] = ref
        if voices:
            keep = set(voices)
            self._refs = {k: v for k, v in self._refs.items() if k in keep}
        if not self._refs:
            raise CloneError(f"no reference clips found in {self.references_dir}")

    def voices(self) -> list[Voice]:
        return [
            Voice(id=vid, label=vid.replace("_", " ").title(), sample=str(path))
            for vid, path in self._refs.items()
        ]

    def synth(self, *, text: str, voice: str) -> Clip:
        ref = self._refs.get(voice)
        if ref is None:
            # Be defensive: the voice map should always resolve, but fall back to
            # the first reference rather than crash mid-episode.
            voice = next(iter(self._refs))
            ref = self._refs[voice]

        if not (text or "").strip():
            return Clip(frames=b"", sample_rate=CLONE_SAMPLE_RATE)

        try:
            import numpy as np

            samples = self._tts.tts(
                text=text,
                speaker_wav=str(ref),
                language=self.language,
                speed=self.speed,
            )
        except Exception as exc:  # pragma: no cover - runtime synth failure
            raise CloneError(f"clone synth failed for voice {voice!r}: {exc}") from exc

        # XTTS yields float32 in [-1, 1]; pack to little-endian signed 16-bit
        # PCM, the format every Clip carries.
        pcm = np.clip(np.asarray(samples, dtype="float32"), -1.0, 1.0)
        frames = (pcm * 32767.0).astype("<i2").tobytes()
        rate = getattr(
            getattr(self._tts, "synthesizer", None),
            "output_sample_rate",
            CLONE_SAMPLE_RATE,
        )
        return Clip(frames=frames, sample_rate=int(rate or CLONE_SAMPLE_RATE))
