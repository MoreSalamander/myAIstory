"""mix — lay verified speech on a timeline and fold resolved cues under/over it.

Runs only after every blocking gate has passed, so it performs no verification;
it renders. These tests use loud, constant-amplitude assets so a placement is
visible as energy added to the speech track at the expected sample offset, and a
ducked bed is visible as *less* energy than the same bed placed plainly.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from myAIstory.mix import DUCK_DB, mix
from myAIstory.schemas.models import Line
from myAIstory.sound import SoundLibrary, resolve_cues
from myAIstory.tts import Clip, ScriptedTTS
from myAIstory.tts.stitch import DEFAULT_GAP_MS

SR = 22050


def _loud_wav(path: Path, *, value: int = 20000, frames: int = SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(int(value).to_bytes(2, "little", signed=True) * frames)


@pytest.fixture
def library(tmp_path: Path) -> SoundLibrary:
    import json
    _loud_wav(tmp_path / "sfx" / "clash.wav", frames=SR // 4)   # 0.25s one-shot
    _loud_wav(tmp_path / "ambience" / "rain.wav", frames=SR)    # 1s loopable bed
    manifest = {"assets": [
        {"tag": "clash", "kind": "sfx", "file": "sfx/clash.wav",
         "gain_db": 0.0, "loop": False, "aliases": []},
        {"tag": "rain", "kind": "ambience", "file": "ambience/rain.wav",
         "gain_db": 0.0, "loop": True, "aliases": []},
    ]}
    (tmp_path / "library.json").write_text(json.dumps(manifest), encoding="utf-8")
    return SoundLibrary.load(tmp_path)


def _speech_clips(n: int, *, frames: int = SR) -> list[Clip]:
    """n silent speech clips (so any energy in the mix comes from cues)."""
    return [Clip(frames=b"\x00\x00" * frames, sample_rate=SR) for _ in range(n)]


def _floats(clip: Clip) -> np.ndarray:
    return np.frombuffer(clip.frames, dtype="<i2").astype(np.float64) / 32768.0


# --- timeline length ---------------------------------------------------------

def test_mix_length_matches_stitched_speech(make_episode, library):
    ep = make_episode(lines=[
        Line(kind="narration", speaker="narrator", text="x"),
        Line(kind="dialogue", speaker="Ember", text="y"),
    ])
    clips = _speech_clips(2)
    plan = resolve_cues(ep, library)  # no cues
    out = mix(ep, clips, plan, library, sample_rate=SR, gap_ms=DEFAULT_GAP_MS)
    gap = int(SR * DEFAULT_GAP_MS / 1000)
    assert out.n_frames == SR + SR + gap          # two clips + one gap, no trailing gap


# --- one-shot sfx placement --------------------------------------------------

def test_oneshot_sfx_lands_at_its_anchor(make_episode, library):
    # cue at idx 0, speech at idx 1: the sfx should add energy to the FIRST
    # second of the timeline (the speech is silent), leaving the rest near zero.
    ep = make_episode(lines=[
        Line(kind="sfx", cue="clash"),                       # idx 0 → anchor 0
        Line(kind="narration", speaker="narrator", text="x"),  # idx 1
        Line(kind="dialogue", speaker="Ember", text="y"),      # idx 2
    ])
    clips = _speech_clips(2)
    plan = resolve_cues(ep, library)
    out = _floats(mix(ep, clips, plan, library, sample_rate=SR))
    head = np.abs(out[: SR // 4]).sum()    # where the 0.25s clash sits
    tail = np.abs(out[SR // 2:]).sum()     # well past the clash
    assert head > 0.0
    assert head > tail * 5                 # energy is concentrated at the anchor


# --- ducking -----------------------------------------------------------------

def test_under_bed_is_quieter_than_plain_bed(make_episode, library):
    lines = [
        Line(kind="ambience", cue="rain"),
        Line(kind="narration", speaker="narrator", text="x"),
        Line(kind="dialogue", speaker="Ember", text="y"),
    ]

    plain = make_episode(lines=lines)
    plain_out = _floats(mix(plain, _speech_clips(2), resolve_cues(plain, library),
                            library, sample_rate=SR))

    ducked_lines = [Line(kind="ambience", cue="rain", under=True), *lines[1:]]
    ducked = make_episode(lines=ducked_lines)
    ducked_out = _floats(mix(ducked, _speech_clips(2), resolve_cues(ducked, library),
                             library, sample_rate=SR))

    # Compare a mid-window away from the fades; the ducked bed must be quieter.
    mid = slice(SR // 2, SR)
    assert np.abs(ducked_out[mid]).sum() < np.abs(plain_out[mid]).sum()


# --- pipeline integration: run_episode with tts + library --------------------

def _episode_json() -> str:
    import json
    return json.dumps({
        "number": 1, "title": "Ep 1", "summary": "Ember meets Ash.",
        "beats": ["opening", "development", "resolution_or_hook"],
        "lines": [
            {"kind": "ambience", "cue": "rain", "under": True},
            {"kind": "narration", "speaker": "narrator",
             "text": " ".join(["dragon"] + ["word"] * 129)},
            {"kind": "sfx", "cue": "clash"},
            {"kind": "sfx", "cue": "kazoo"},               # unknown → dropped
            {"kind": "dialogue", "speaker": "Ember", "text": "Mine."},
            {"kind": "dialogue", "speaker": "Ash", "text": "Never."},
        ],
        "new_facts": [],
    })


def test_run_episode_with_library_mixes_and_logs_cues(bible, library):
    from myAIstory.events import EventEmitter
    from myAIstory.pipeline.episode import run_episode
    from myAIstory.synth import ScriptedLLM

    events: list[dict] = []
    emit = EventEmitter([events.append])
    llm = ScriptedLLM({"episode_draft": [_episode_json()]})

    ep = run_episode("sid", 1, llm, emit, bible=bible, target_minutes=1,
                     tts=ScriptedTTS(), library=library, persist=False)
    assert ep is not None

    types = [e["type"] for e in events]
    placed = [e for e in events if e["type"] == "cue_place"]
    dropped = [e for e in events if e["type"] == "cue_drop"]
    assert {p["cue"] for p in placed} == {"rain", "clash"}
    assert [d["cue"] for d in dropped] == ["kazoo"]       # non-blocking drop
    assert "mix" in [e.get("stage") for e in events]      # mixed, not just stitched
    assert "stitch" not in [e.get("stage") for e in events]
    assert "done" in types
