"""Piper — the first concrete local TTS backend (CONSTITUTION: local-only).

Piper (https://github.com/rhasspy/piper) is a fast, fully-offline neural TTS
that runs as a CLI: text in on stdin, raw 16-bit mono PCM out on stdout with
`--output-raw`. Each voice is an `.onnx` model file plus an `.onnx.json` config
that declares the model's sample rate.

This backend is a thin adapter — it shells out per line and wraps the PCM in a
`Clip`. It implements the same `TTSEngine` protocol as ScriptedTTS, so the
pipeline cannot tell them apart. Nothing here is exercised until a Piper binary
and at least one voice model are installed; until then ScriptedTTS covers the
audio path in tests.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from myAIstory.tts.base import Clip, Voice


class PiperError(RuntimeError):
    pass


class PiperTTS:
    """Render lines with local Piper voice models.

    `voices_dir` holds `<id>.onnx` + `<id>.onnx.json` pairs. The voice `id` is
    the file stem, so `voice_assign`'s casting maps onto whatever models are
    installed. `narrator_voice` lets a series pin a specific model for
    narration; otherwise the first voice id is used.
    """

    def __init__(
        self,
        voices_dir: str | Path,
        *,
        binary: str = "piper",
        length_scale: float | None = None,
    ) -> None:
        self.voices_dir = Path(voices_dir)
        self.binary = binary
        self.length_scale = length_scale
        self._models: dict[str, Path] = {}
        self._rates: dict[str, int] = {}
        self._discover()

    def _discover(self) -> None:
        if not self.voices_dir.is_dir():
            raise PiperError(f"piper voices dir not found: {self.voices_dir}")
        for model in sorted(self.voices_dir.glob("*.onnx")):
            vid = model.stem
            self._models[vid] = model
            rate = 22050
            cfg = model.with_suffix(".onnx.json")
            if cfg.exists():
                try:
                    data = json.loads(cfg.read_text(encoding="utf-8"))
                    rate = int(data.get("audio", {}).get("sample_rate", rate))
                except (ValueError, OSError):
                    pass
            self._rates[vid] = rate
        if not self._models:
            raise PiperError(f"no .onnx voices found in {self.voices_dir}")

    def voices(self) -> list[Voice]:
        return [Voice(id=vid, label=vid.replace("_", " ").title())
                for vid in self._models]

    def synth(self, *, text: str, voice: str) -> Clip:
        model = self._models.get(voice)
        if model is None:
            # Fall back to the first model rather than crash mid-episode; the
            # voice map should always resolve, but be defensive about it.
            voice = next(iter(self._models))
            model = self._models[voice]

        cmd = [self.binary, "--model", str(model), "--output-raw"]
        if self.length_scale is not None:
            cmd += ["--length_scale", str(self.length_scale)]
        try:
            proc = subprocess.run(
                cmd,
                input=(text or "").encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        except FileNotFoundError as exc:
            raise PiperError(f"piper binary not found: {self.binary!r}") from exc
        except subprocess.CalledProcessError as exc:
            msg = exc.stderr.decode("utf-8", "ignore").strip()
            raise PiperError(f"piper failed for voice {voice!r}: {msg}") from exc

        return Clip(frames=proc.stdout, sample_rate=self._rates[voice])
