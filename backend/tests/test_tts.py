"""TTS layer: Clip encoding, ScriptedTTS, stitch, and the render stage.

All offline — ScriptedTTS yields silent PCM, so the per-line render loop and
the stitch concatenation are exercised with no audio engine, the same way
ScriptedLLM drives the pipeline with no Ollama.
"""

from __future__ import annotations

import io
import wave

import pytest

from myAIstory.events import EventEmitter
from myAIstory.pipeline.audio import render_episode, voice_for
from myAIstory.pipeline.episode import run_episode
from myAIstory.schemas.models import Line
from myAIstory.synth import ScriptedLLM
from myAIstory.tts import Clip, ScriptedTTS, stitch
from myAIstory.tts.stitch import DEFAULT_GAP_MS


def _capture() -> tuple[list[dict], EventEmitter]:
    events: list[dict] = []
    return events, EventEmitter([events.append])


def _types(events: list[dict]) -> list[str]:
    return [e["type"] for e in events]


# --- Clip --------------------------------------------------------------------

def test_clip_duration_and_frames():
    # 22050 samples of 16-bit mono = 1.0 s.
    clip = Clip(frames=b"\x00\x00" * 22050, sample_rate=22050)
    assert clip.n_frames == 22050
    assert clip.duration == pytest.approx(1.0)


def test_clip_to_wav_roundtrips():
    clip = Clip(frames=b"\x01\x02" * 100, sample_rate=22050)
    with wave.open(io.BytesIO(clip.to_wav()), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == 22050
        assert w.readframes(w.getnframes()) == clip.frames


# --- ScriptedTTS -------------------------------------------------------------

def test_scripted_voices_registry():
    eng = ScriptedTTS()
    ids = {v.id for v in eng.voices()}
    assert "narrator" in ids and "voice_00" in ids


def test_scripted_synth_scales_with_words():
    eng = ScriptedTTS(words_per_second=2.5, sample_rate=22050)
    short = eng.synth(text="one two", voice="narrator")        # 2 words
    long = eng.synth(text="a b c d e f g h", voice="narrator")  # 8 words
    assert long.n_frames > short.n_frames
    assert eng.calls == [("narrator", "one two"), ("narrator", "a b c d e f g h")]


def test_scripted_empty_text_still_produces_a_clip():
    clip = ScriptedTTS().synth(text="", voice="narrator")
    assert clip.n_frames > 0  # floors at one word of silence


# --- stitch ------------------------------------------------------------------

def test_stitch_concatenates_with_gaps():
    a = Clip(frames=b"\x00\x00" * 100, sample_rate=22050)
    b = Clip(frames=b"\x00\x00" * 200, sample_rate=22050)
    out = stitch([a, b], gap_ms=DEFAULT_GAP_MS)
    gap_frames = int(22050 * DEFAULT_GAP_MS / 1000)
    assert out.n_frames == 100 + 200 + gap_frames  # one gap between two clips


def test_stitch_single_clip_has_no_gap():
    a = Clip(frames=b"\x00\x00" * 100, sample_rate=22050)
    assert stitch([a]).n_frames == 100


def test_stitch_rejects_empty():
    with pytest.raises(ValueError):
        stitch([])


def test_stitch_rejects_format_mismatch():
    a = Clip(frames=b"\x00\x00" * 10, sample_rate=22050)
    b = Clip(frames=b"\x00\x00" * 10, sample_rate=16000)
    with pytest.raises(ValueError):
        stitch([a, b])


# --- voice resolution + render ----------------------------------------------

def test_voice_for_resolves_narration_and_dialogue(voice_map):
    narr = Line(kind="narration", speaker="narrator", text="...")
    dlg = Line(kind="dialogue", speaker="Ember", text="...")
    assert voice_for(narr, voice_map) == voice_map.narrator
    assert voice_for(dlg, voice_map) == voice_map.by_character["Ember"]


def test_render_emits_one_tts_line_per_speech_line(make_episode, voice_map):
    events, emit = _capture()
    clip = render_episode(make_episode(), voice_map, ScriptedTTS(), emit)
    tts = [e for e in events if e["type"] == "tts_line"]
    assert [e["idx"] for e in tts] == [0, 1, 2]
    assert [e["voice"] for e in tts] == [
        voice_map.narrator,
        voice_map.by_character["Ember"],
        voice_map.by_character["Ash"],
    ]
    assert "tts_synth" in [e.get("stage") for e in events]
    assert clip.duration > 0


def test_render_skips_cue_lines(make_episode, voice_map):
    events, emit = _capture()
    ep = make_episode(lines=[
        Line(kind="sfx", cue="thunder"),                      # phase-2 cue: skipped
        Line(kind="narration", speaker="narrator", text="a b c"),
        Line(kind="dialogue", speaker="Ember", text="d e"),
    ])
    render_episode(ep, voice_map, ScriptedTTS(), emit)
    assert len([e for e in events if e["type"] == "tts_line"]) == 2  # cue not rendered


# --- pipeline integration ----------------------------------------------------

def _episode_json() -> str:
    import json
    return json.dumps({
        "number": 1, "title": "Ep 1", "summary": "Ember meets Ash.",
        "beats": ["opening", "development", "resolution_or_hook"],
        "lines": [
            {"kind": "narration", "speaker": "narrator",
             "text": " ".join(["dragon"] + ["word"] * 129)},
            {"kind": "dialogue", "speaker": "Ember", "text": "Mine."},
            {"kind": "dialogue", "speaker": "Ash", "text": "Never."},
        ],
        "new_facts": [],
    })


def test_run_episode_with_tts_renders_audio(bible):
    events, emit = _capture()
    llm = ScriptedLLM({"episode_draft": [_episode_json()]})
    ep = run_episode("sid", 1, llm, emit, bible=bible, target_minutes=1,
                     tts=ScriptedTTS(), persist=False)
    assert ep is not None
    t = _types(events)
    assert "tts_line" in t
    assert any(e.get("stage") == "stitch" for e in events)


def test_run_episode_without_tts_skips_audio(bible):
    events, emit = _capture()
    llm = ScriptedLLM({"episode_draft": [_episode_json()]})
    ep = run_episode("sid", 1, llm, emit, bible=bible, target_minutes=1,
                     persist=False)
    assert ep is not None
    assert "tts_line" not in _types(events)  # phase-2 behavior preserved
