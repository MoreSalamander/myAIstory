"""Voice cloning — match a short reference clip (CONSTITUTION: local-only).

Where Piper and Kokoro speak in fixed, built-in timbres, a cloning model takes
a *reference clip* you supply (a few seconds of clean speech) and renders new
lines in that voice. So to cast a deep, sexy narrator you just drop a sample of
that voice into the references directory — the model matches its timbre. This
adapter wraps **Chatterbox** (Resemble AI), among the best-sounding open local
TTS models: zero-shot cloning from a short clip plus an `exaggeration` control
that dials delivery intensity (great for a sultry read). The same seam could
host F5-TTS or XTTS later by swapping the model load + the synth call.

Like the other backends this is a thin adapter implementing the `TTSEngine`
protocol, so the pipeline cannot tell it apart: each reference file is a
castable "voice" (id = file stem), `voice_assign` maps characters onto whatever
references you provide, and `stitch` concatenates the clips. Chatterbox emits a
float tensor; `synth` packs that into the same signed-16-bit mono PCM `Clip`
every backend produces.

A references directory holds one audio file per voice::

    <references_dir>/narrator.wav     a few seconds of the target voice
    <references_dir>/ember.flac       (any of .wav/.flac/.mp3/.ogg)

Nothing here runs until both the reference clips and the `chatterbox-tts`
package are present (the model weights are fetched once into the HF cache on
first use); until then ScriptedTTS covers the audio path in tests — the same
swap-the-backend discipline PiperTTS and KokoroTTS follow.
"""

from __future__ import annotations

from pathlib import Path

from myAIstory.tts.base import Clip, Voice

CLONE_SAMPLE_RATE = 24000  # Chatterbox renders at 24 kHz
REFERENCE_EXTS = (".wav", ".flac", ".mp3", ".ogg")


class CloneError(RuntimeError):
    pass


def _auto_device() -> str:
    """Prefer Apple-Silicon MPS, then CUDA, else CPU — best available locally."""
    try:
        import torch
    except ImportError:  # pragma: no cover - depends on optional dep
        return "cpu"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():  # pragma: no cover - no GPU in CI
        return "cuda"
    return "cpu"


class CloneTTS:
    """Render lines by cloning short reference clips with Chatterbox.

    `references_dir` holds one audio file per voice (`<id>.wav`); the voice `id`
    is the file stem, so deterministic casting maps characters onto whatever
    references you drop in. `exaggeration` (0-1+) scales emotional intensity and
    `cfg_weight` trades pace against fidelity — both are Chatterbox knobs; the
    defaults match a natural read. The heavy model is loaded lazily so the
    package stays importable without the optional dependency.
    """

    def __init__(
        self,
        references_dir: str | Path,
        *,
        device: str | None = None,
        exaggeration: float = 0.5,
        cfg_weight: float = 0.5,
        voices: list[str] | None = None,
    ) -> None:
        self.references_dir = Path(references_dir)
        self.exaggeration = exaggeration
        self.cfg_weight = cfg_weight
        self._refs: dict[str, Path] = {}
        self._discover(voices)

        try:
            from chatterbox.tts import ChatterboxTTS  # lazy: only for real synth
        except ImportError as exc:  # pragma: no cover - depends on optional dep
            raise CloneError(
                "chatterbox-tts is not installed (pip install chatterbox-tts)"
            ) from exc

        self.device = device or _auto_device()
        try:
            self._model = ChatterboxTTS.from_pretrained(device=self.device)
        except Exception as exc:  # pragma: no cover - model load failure
            raise CloneError(f"failed to load chatterbox model: {exc}") from exc

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

    @property
    def sample_rate(self) -> int:
        return int(getattr(self._model, "sr", CLONE_SAMPLE_RATE) or CLONE_SAMPLE_RATE)

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
            return Clip(frames=b"", sample_rate=self.sample_rate)

        try:
            import numpy as np

            wav = self._model.generate(
                text,
                audio_prompt_path=str(ref),
                exaggeration=self.exaggeration,
                cfg_weight=self.cfg_weight,
            )
        except Exception as exc:  # pragma: no cover - runtime synth failure
            raise CloneError(f"clone synth failed for voice {voice!r}: {exc}") from exc

        # Chatterbox returns a float tensor (shape (1, n) or (n,)) in [-1, 1];
        # flatten to numpy and pack to little-endian signed 16-bit PCM, the
        # format every Clip carries.
        samples = np.asarray(getattr(wav, "cpu", lambda: wav)(), dtype="float32")
        samples = samples.reshape(-1)
        pcm = np.clip(samples, -1.0, 1.0)
        frames = (pcm * 32767.0).astype("<i2").tobytes()
        return Clip(frames=frames, sample_rate=self.sample_rate)
