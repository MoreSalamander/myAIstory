"""CloneTTS — the XTTS-v2 voice-cloning backend.

The real XTTS model is a large optional (torch-based) download, so these tests
fake the `TTS` dependency (injected into sys.modules) to exercise the adapter's
own logic: it stays inert until reference clips exist, treats each reference
file as a castable voice, clones the right reference per line, and packs XTTS's
float32 output into the same signed-16-bit PCM Clip every backend produces.
"""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from myAIstory.tts import Clip, CloneError, CloneTTS
from myAIstory.tts.base import TTSEngine


def _make_refs_dir(tmp_path):
    # Deliberately unsorted + a non-audio file that must be ignored.
    (tmp_path / "narrator.wav").write_bytes(b"fake")
    (tmp_path / "ember.flac").write_bytes(b"fake")
    (tmp_path / "notes.txt").write_text("ignore me")
    return tmp_path


class _FakeSynthesizer:
    output_sample_rate = 24000


class _FakeTTS:
    last: dict = {}

    def __init__(self, model, progress_bar=False, gpu=False):
        self.model = model
        self.synthesizer = _FakeSynthesizer()

    def tts(self, text, speaker_wav, language, speed):
        _FakeTTS.last = {
            "text": text,
            "speaker_wav": speaker_wav,
            "language": language,
            "speed": speed,
        }
        n = max(1, len((text or "").split()))
        return np.linspace(-1.0, 1.0, n * 4, dtype="float32")


@pytest.fixture
def fake_tts(monkeypatch):
    pkg = types.ModuleType("TTS")
    api = types.ModuleType("TTS.api")
    api.TTS = _FakeTTS
    pkg.api = api
    monkeypatch.setitem(sys.modules, "TTS", pkg)
    monkeypatch.setitem(sys.modules, "TTS.api", api)
    return api


def test_clone_requires_references(tmp_path, fake_tts):
    # Inert until at least one reference clip is present — mirrors PiperTTS.
    with pytest.raises(CloneError):
        CloneTTS(tmp_path)


def test_clone_is_a_tts_engine(tmp_path, fake_tts):
    eng = CloneTTS(_make_refs_dir(tmp_path))
    assert isinstance(eng, TTSEngine)


def test_clone_voice_registry_from_references(tmp_path, fake_tts):
    eng = CloneTTS(_make_refs_dir(tmp_path))
    # File stems become voice ids, sorted; non-audio files are ignored.
    assert [v.id for v in eng.voices()] == ["ember", "narrator"]
    assert all(v.sample for v in eng.voices())  # each carries its reference path


def test_clone_synth_clones_the_right_reference(tmp_path, fake_tts):
    eng = CloneTTS(_make_refs_dir(tmp_path))
    eng.synth(text="come closer", voice="narrator")
    assert _FakeTTS.last["speaker_wav"].endswith("narrator.wav")
    assert _FakeTTS.last["language"] == "en"


def test_clone_synth_packs_int16_pcm(tmp_path, fake_tts):
    eng = CloneTTS(_make_refs_dir(tmp_path))
    clip = eng.synth(text="hello there", voice="ember")
    assert isinstance(clip, Clip)
    assert clip.sample_rate == 24000 and clip.sample_width == 2 and clip.channels == 1
    arr = np.frombuffer(clip.frames, dtype="<i2")
    assert arr[0] == -32767 and arr[-1] == 32767  # ramp endpoints survive packing


def test_clone_unknown_voice_falls_back(tmp_path, fake_tts):
    eng = CloneTTS(_make_refs_dir(tmp_path))
    eng.synth(text="hi", voice="does_not_exist")
    assert _FakeTTS.last["speaker_wav"].endswith("ember.flac")  # first registry voice


def test_clone_empty_text_is_silent(tmp_path, fake_tts):
    eng = CloneTTS(_make_refs_dir(tmp_path))
    clip = eng.synth(text="   ", voice="narrator")
    assert clip.frames == b"" and clip.sample_rate == 24000
