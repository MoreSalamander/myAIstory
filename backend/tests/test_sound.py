"""SoundLibrary + cue_verify — the curated registry and the one non-blocking gate.

A cue the model emits is an untrusted proposal: it only becomes audio if its tag
(or a known alias) is in the human-owned manifest. Resolution is a pure lookup —
no LLM, no network — and resolution failure DROPS the cue rather than failing the
episode. These tests pin both halves of that contract.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from myAIstory.schemas.models import Line
from myAIstory.sound import CuePlan, SoundLibrary, resolve_cues


def _write_wav(path: Path, *, sample_rate: int = 22050, frames: int = 100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x10\x00" * frames)


@pytest.fixture
def library(tmp_path: Path) -> SoundLibrary:
    """A tiny on-disk library: one sfx (with alias) and one looping bed."""
    _write_wav(tmp_path / "sfx" / "thunder.wav")
    _write_wav(tmp_path / "ambience" / "rain.wav")
    manifest = {
        "assets": [
            {"tag": "thunder", "kind": "sfx", "file": "sfx/thunder.wav",
             "gain_db": -2.0, "loop": False, "aliases": ["storm", "thunderclap"]},
            {"tag": "rain", "kind": "ambience", "file": "ambience/rain.wav",
             "gain_db": -6.0, "loop": True, "aliases": []},
        ]
    }
    (tmp_path / "library.json").write_text(json.dumps(manifest), encoding="utf-8")
    return SoundLibrary.load(tmp_path)


# --- library load + resolve --------------------------------------------------

def test_load_exposes_tags(library):
    assert set(library.tags) == {"thunder", "rain"}


def test_resolve_by_tag(library):
    asset = library.resolve("thunder")
    assert asset is not None and asset.kind == "sfx" and asset.loop is False


def test_resolve_is_case_and_whitespace_insensitive(library):
    assert library.resolve("  THUNDER ") is library.resolve("thunder")


def test_resolve_by_alias(library):
    assert library.resolve("storm") is library.resolve("thunder")


def test_resolve_unknown_returns_none(library):
    assert library.resolve("kazoo") is None
    assert library.resolve(None) is None


def test_load_clip_reads_pcm(library):
    asset = library.resolve("rain")
    clip = library.load_clip(asset)
    assert clip.sample_rate == 22050
    assert clip.n_frames == 100


# --- cue_verify (resolve_cues) is non-blocking -------------------------------

def _episode(lines, make_episode):
    return make_episode(lines=lines)


def test_resolve_places_known_cues(make_episode, library):
    ep = make_episode(lines=[
        Line(kind="ambience", cue="rain", under=True),
        Line(kind="narration", speaker="narrator", text="a b c"),
        Line(kind="sfx", cue="thunder"),
    ])
    plan = resolve_cues(ep, library)
    assert isinstance(plan, CuePlan)
    assert [p.asset.tag for p in plan.placements] == ["rain", "thunder"]
    assert plan.placements[0].under is True          # bed carries its `under` flag
    assert plan.placements[0].idx == 0               # idx is the timeline anchor
    assert plan.drops == []
    assert plan.has_cues


def test_resolve_drops_unknown_cue_without_failing(make_episode, library):
    ep = make_episode(lines=[
        Line(kind="sfx", cue="kazoo"),               # not in catalog → dropped
        Line(kind="narration", speaker="narrator", text="a b c"),
    ])
    plan = resolve_cues(ep, library)
    assert plan.placements == []
    assert [(d.kind, d.cue) for d in plan.drops] == [("sfx", "kazoo")]
    assert not plan.has_cues                          # nothing to mix, episode survives


def test_resolve_ignores_speech_lines(make_episode, library):
    ep = make_episode()  # default episode: all speech, no cues
    plan = resolve_cues(ep, library)
    assert plan.placements == [] and plan.drops == []
