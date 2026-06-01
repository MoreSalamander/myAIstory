"""KokoroTTS — the higher-fidelity local backend.

The real Kokoro model is a large optional download, so these tests fake the
`kokoro_onnx` dependency (injected into sys.modules) to exercise the adapter's
own logic: it stays inert until the model files exist, reports a stable voice
registry, infers language per voice, and packs Kokoro's float32 output into the
same signed-16-bit PCM Clip every backend produces.
"""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from myAIstory.tts import Clip, KokoroError, KokoroTTS
from myAIstory.tts.base import TTSEngine


def _make_model_dir(tmp_path):
    (tmp_path / "kokoro-v1.0.onnx").write_bytes(b"fake")
    (tmp_path / "voices-v1.0.bin").write_bytes(b"fake")
    return tmp_path


class _FakeKokoro:
    last: dict = {}

    def __init__(self, model, voices):
        self.model, self.voices_file = model, voices

    def get_voices(self):
        return ["am_michael", "af_heart", "bf_emma"]  # deliberately unsorted

    def create(self, text, voice, speed, lang):
        _FakeKokoro.last = {"text": text, "voice": voice, "speed": speed, "lang": lang}
        n = max(1, len((text or "").split()))
        samples = np.linspace(-1.0, 1.0, n * 4, dtype="float32")
        return samples, 24000


@pytest.fixture
def fake_kokoro(monkeypatch):
    mod = types.ModuleType("kokoro_onnx")
    mod.Kokoro = _FakeKokoro
    monkeypatch.setitem(sys.modules, "kokoro_onnx", mod)
    return mod


def test_kokoro_requires_model_files(tmp_path):
    # Inert until the model files are present — mirrors PiperTTS.
    with pytest.raises(KokoroError):
        KokoroTTS(tmp_path)


def test_kokoro_is_a_tts_engine(tmp_path, fake_kokoro):
    eng = KokoroTTS(_make_model_dir(tmp_path))
    assert isinstance(eng, TTSEngine)


def test_kokoro_voice_registry_is_sorted(tmp_path, fake_kokoro):
    eng = KokoroTTS(_make_model_dir(tmp_path))
    assert [v.id for v in eng.voices()] == ["af_heart", "am_michael", "bf_emma"]


def test_kokoro_synth_packs_int16_pcm(tmp_path, fake_kokoro):
    eng = KokoroTTS(_make_model_dir(tmp_path))
    clip = eng.synth(text="hello there", voice="am_michael")
    assert isinstance(clip, Clip)
    assert clip.sample_rate == 24000 and clip.sample_width == 2 and clip.channels == 1
    arr = np.frombuffer(clip.frames, dtype="<i2")
    assert arr[0] == -32767 and arr[-1] == 32767  # ramp endpoints survive packing


def test_kokoro_infers_language_from_voice(tmp_path, fake_kokoro):
    eng = KokoroTTS(_make_model_dir(tmp_path))
    eng.synth(text="cheerio", voice="bf_emma")
    assert _FakeKokoro.last["lang"] == "en-gb"  # b* = British English
    eng.synth(text="howdy", voice="af_heart")
    assert _FakeKokoro.last["lang"] == "en-us"


def test_kokoro_unknown_voice_falls_back(tmp_path, fake_kokoro):
    eng = KokoroTTS(_make_model_dir(tmp_path))
    eng.synth(text="hi", voice="does_not_exist")
    assert _FakeKokoro.last["voice"] == "af_heart"  # first registry voice


def test_kokoro_empty_text_is_silent(tmp_path, fake_kokoro):
    eng = KokoroTTS(_make_model_dir(tmp_path))
    clip = eng.synth(text="   ", voice="am_michael")
    assert clip.frames == b"" and clip.sample_rate == 24000
