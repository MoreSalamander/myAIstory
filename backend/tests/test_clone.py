"""CloneTTS — the Chatterbox voice-cloning backend.

The real Chatterbox model is a large optional (torch-based) download, so these
tests fake the `chatterbox` dependency (injected into sys.modules) to exercise
the adapter's own logic: it stays inert until reference clips exist, treats each
reference file as a castable voice, clones the right reference per line, and
packs Chatterbox's float-tensor output into the same signed-16-bit PCM Clip
every backend produces. `device="cpu"` is passed explicitly so the adapter
never touches torch during tests.
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


class _FakeTensor:
    """Stand-in for the torch tensor Chatterbox returns (shape (1, n))."""

    def __init__(self, arr):
        self._arr = np.asarray(arr, dtype="float32").reshape(1, -1)

    def cpu(self):
        return self._arr  # numpy view; CloneTTS flattens + clips


class _FakeChatterbox:
    last: dict = {}
    sr = 24000

    @classmethod
    def from_pretrained(cls, device):
        inst = cls()
        inst.device = device
        return inst

    def generate(self, text, audio_prompt_path, exaggeration, cfg_weight):
        _FakeChatterbox.last = {
            "text": text,
            "audio_prompt_path": audio_prompt_path,
            "exaggeration": exaggeration,
            "cfg_weight": cfg_weight,
        }
        n = max(1, len((text or "").split()))
        return _FakeTensor(np.linspace(-1.0, 1.0, n * 4, dtype="float32"))


@pytest.fixture
def fake_chatterbox(monkeypatch):
    pkg = types.ModuleType("chatterbox")
    tts_mod = types.ModuleType("chatterbox.tts")
    tts_mod.ChatterboxTTS = _FakeChatterbox
    pkg.tts = tts_mod
    monkeypatch.setitem(sys.modules, "chatterbox", pkg)
    monkeypatch.setitem(sys.modules, "chatterbox.tts", tts_mod)
    return tts_mod


def _engine(refs_dir):
    # Explicit device="cpu" keeps the adapter off torch during tests.
    return CloneTTS(refs_dir, device="cpu")


def test_clone_requires_references(tmp_path, fake_chatterbox):
    # Inert until at least one reference clip is present — mirrors PiperTTS.
    with pytest.raises(CloneError):
        _engine(tmp_path)


def test_clone_is_a_tts_engine(tmp_path, fake_chatterbox):
    assert isinstance(_engine(_make_refs_dir(tmp_path)), TTSEngine)


def test_clone_voice_registry_from_references(tmp_path, fake_chatterbox):
    eng = _engine(_make_refs_dir(tmp_path))
    # File stems become voice ids, sorted; non-audio files are ignored.
    assert [v.id for v in eng.voices()] == ["ember", "narrator"]
    assert all(v.sample for v in eng.voices())  # each carries its reference path


def test_clone_synth_clones_the_right_reference(tmp_path, fake_chatterbox):
    eng = _engine(_make_refs_dir(tmp_path))
    eng.synth(text="come closer", voice="narrator")
    assert _FakeChatterbox.last["audio_prompt_path"].endswith("narrator.wav")
    assert _FakeChatterbox.last["exaggeration"] == 0.5  # default delivery


def test_clone_synth_packs_int16_pcm(tmp_path, fake_chatterbox):
    eng = _engine(_make_refs_dir(tmp_path))
    clip = eng.synth(text="hello there", voice="ember")
    assert isinstance(clip, Clip)
    assert clip.sample_rate == 24000 and clip.sample_width == 2 and clip.channels == 1
    arr = np.frombuffer(clip.frames, dtype="<i2")
    assert arr[0] == -32767 and arr[-1] == 32767  # ramp endpoints survive packing


def test_clone_unknown_voice_falls_back(tmp_path, fake_chatterbox):
    eng = _engine(_make_refs_dir(tmp_path))
    eng.synth(text="hi", voice="does_not_exist")
    assert _FakeChatterbox.last["audio_prompt_path"].endswith("ember.flac")  # first voice


def test_clone_empty_text_is_silent(tmp_path, fake_chatterbox):
    eng = _engine(_make_refs_dir(tmp_path))
    clip = eng.synth(text="   ", voice="narrator")
    assert clip.frames == b"" and clip.sample_rate == 24000


def test_clone_exaggeration_is_configurable(tmp_path, fake_chatterbox):
    eng = CloneTTS(_make_refs_dir(tmp_path), device="cpu", exaggeration=0.9)
    eng.synth(text="sultry", voice="narrator")
    assert _FakeChatterbox.last["exaggeration"] == 0.9  # the sexy-delivery knob
