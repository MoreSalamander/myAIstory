"""Pipeline orchestration: drafting + gating + bounded-retry-then-skip.

Driven entirely by ScriptedLLM, so the whole pipeline runs with no Ollama. All
runs use persist=False — these tests exercise control flow, not storage.
"""

from __future__ import annotations

import json

from myAIstory.events import EventEmitter
from myAIstory.pipeline import run_episode, run_init, run_series
from myAIstory.synth import ScriptedLLM


# --- canned model output -----------------------------------------------------

def frame_json(theme: str = "dragons") -> str:
    """A bible FRAME — cast + world, arc deliberately empty (planned per-beat)."""
    return json.dumps({
        "series_id": "ignored-overwritten-by-slug",
        "title": "The Ember Cycle",
        "theme": theme,
        "tone": "epic",
        "characters": [
            {"name": "Ember", "aliases": [], "role": "protagonist",
             "status": "alive", "facts": []},
            {"name": "Ash", "aliases": [], "role": "rival",
             "status": "alive", "facts": []},
        ],
        "world_facts": [],
        "arc": [],
        "episode_count": 2,
    })


def arc_beat_json(episode: int, summary: str | None = None) -> str:
    return json.dumps({"episode": episode,
                       "summary": summary or f"Episode {episode} beat (dragons)."})


def arc_beats(n: int = 2) -> list[str]:
    """One canned beat response per episode for the arc map step."""
    return [arc_beat_json(k) for k in range(1, n + 1)]


def episode_json(number: int = 1, beats=None, words: int = 130) -> str:
    narration = " ".join(["dragon"] + ["word"] * (words - 1))
    return json.dumps({
        "number": number,
        "title": f"Ep {number}",
        "summary": "Ember meets Ash.",
        "beats": beats or ["opening", "development", "resolution_or_hook"],
        "lines": [
            {"kind": "narration", "speaker": "narrator", "text": narration},
            {"kind": "dialogue", "speaker": "Ember", "text": "Mine."},
            {"kind": "dialogue", "speaker": "Ash", "text": "Never."},
        ],
        "new_facts": [],
    })


def bad_episode_json(number: int = 1) -> str:
    # Missing the required resolution_or_hook beat → structure_verify fails.
    return episode_json(number=number, beats=["opening", "development"])


def _capture() -> tuple[list[dict], EventEmitter]:
    events: list[dict] = []
    return events, EventEmitter([events.append])


def _types(events: list[dict]) -> list[str]:
    return [e["type"] for e in events]


# --- run_init ----------------------------------------------------------------

def test_init_success(seed):
    events, emit = _capture()
    llm = ScriptedLLM({"bible_draft": [frame_json()], "arc_beat": arc_beats(2)})
    bible = run_init(seed.model_dump(), llm, emit, persist=False)
    assert bible is not None
    assert bible.theme == "dragons"
    assert bible.series_id == "the-ember-cycle"  # pinned to deterministic slug
    assert [b.episode for b in bible.arc] == [1, 2]  # arc assembled from the map
    assert "verify_pass" in _types(events)


def test_init_rejects_bad_seed(seed):
    events, emit = _capture()
    raw = seed.model_dump()
    raw["characters"].append({"name": "ember"})  # duplicate → seed_validate fails
    llm = ScriptedLLM({})  # must never be called
    bible = run_init(raw, llm, emit, persist=False)
    assert bible is None
    assert llm.calls == []
    assert any(e["type"] == "done" and e["result"] == "rejected" for e in events)


def test_init_frame_retries_then_succeeds(seed):
    events, emit = _capture()
    llm = ScriptedLLM({"bible_draft": [frame_json(theme="vampires"), frame_json()],
                       "arc_beat": arc_beats(2)})
    bible = run_init(seed.model_dump(), llm, emit, max_retries=2, persist=False)
    assert bible is not None and bible.theme == "dragons"
    # 2 frame calls (1 bad + 1 good) + 2 beat calls (one per episode).
    assert len(llm.calls) == 4
    t = _types(events)
    assert "verify_fail" in t and "retry" in t and "verify_pass" in t


def test_init_skips_after_frame_budget(seed):
    events, emit = _capture()
    llm = ScriptedLLM({"bible_draft": [frame_json(theme="vampires")] * 3})
    bible = run_init(seed.model_dump(), llm, emit, max_retries=2, persist=False)
    assert bible is None
    assert len(llm.calls) == 3  # initial + 2 retries, arc never reached
    assert any(e["type"] == "skip" for e in events)


def test_init_arc_beat_retries_then_succeeds(seed):
    events, emit = _capture()
    # Episode-2 beat is mislabeled "3" the first time → arc_verify fails, retry.
    llm = ScriptedLLM({
        "bible_draft": [frame_json()],
        "arc_beat": [arc_beat_json(1), arc_beat_json(3), arc_beat_json(2)],
    })
    bible = run_init(seed.model_dump(), llm, emit, max_retries=2, persist=False)
    assert bible is not None
    assert [b.episode for b in bible.arc] == [1, 2]
    assert "retry" in _types(events)


def test_init_skips_when_arc_beat_exhausts_budget(seed):
    events, emit = _capture()
    # The episode-1 beat is always mislabeled → arc_verify never passes.
    llm = ScriptedLLM({
        "bible_draft": [frame_json()],
        "arc_beat": [arc_beat_json(9)] * 3,
    })
    bible = run_init(seed.model_dump(), llm, emit, max_retries=2, persist=False)
    assert bible is None
    assert any(e["type"] == "skip" and e.get("stage") == "arc_plan" for e in events)


# --- run_episode -------------------------------------------------------------

def test_episode_success(bible):
    events, emit = _capture()
    llm = ScriptedLLM({"episode_draft": [episode_json(1)]})
    ep = run_episode("sid", 1, llm, emit, bible=bible, target_minutes=1, persist=False)
    assert ep is not None and ep.number == 1
    assert any(e["type"] == "done" and e["result"] == "ok" for e in events)


def test_episode_retries_then_succeeds(bible):
    events, emit = _capture()
    llm = ScriptedLLM({"episode_draft": [bad_episode_json(1), episode_json(1)]})
    ep = run_episode("sid", 1, llm, emit, bible=bible, target_minutes=1,
                     max_retries=2, persist=False)
    assert ep is not None
    assert len(llm.calls) == 2
    assert "retry" in _types(events)


def test_episode_skips_after_budget(bible):
    events, emit = _capture()
    llm = ScriptedLLM({"episode_draft": [bad_episode_json(1)] * 3})
    ep = run_episode("sid", 1, llm, emit, bible=bible, target_minutes=1,
                     max_retries=2, persist=False)
    assert ep is None
    assert any(e["type"] == "skip" for e in events)


def test_episode_json_parse_failure_retries(bible):
    events, emit = _capture()
    llm = ScriptedLLM({"episode_draft": ["not json at all", episode_json(1)]})
    ep = run_episode("sid", 1, llm, emit, bible=bible, target_minutes=1,
                     max_retries=2, persist=False)
    assert ep is not None
    fails = [e for e in events if e["type"] == "verify_fail"]
    assert any("json_parse" in v for e in fails for v in e["violations"])


# --- bible_update: the verified canon-growth stage ---------------------------

def _episode_with_canon_updates(number: int = 1) -> str:
    """A valid episode that proposes a new character and a death."""
    base = json.loads(episode_json(number=number))
    base["new_facts"] = ["The hoard was older than the volcano."]
    base["new_characters"] = [
        {"name": "Vesh", "role": "guard captain", "status": "alive"},
        {"name": "ember", "role": "dup"},   # collides (case-insensitive) → skipped
    ]
    base["deaths"] = ["Ash"]
    return json.dumps(base)


def test_bible_update_grows_canon(bible, tmp_path, monkeypatch):
    import myAIstory.store as store
    monkeypatch.setattr(store, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(store, "SERIES_ROOT", tmp_path / "series")

    events, emit = _capture()
    llm = ScriptedLLM({"episode_draft": [_episode_with_canon_updates(1)]})
    ep = run_episode(bible.series_id, 1, llm, emit, bible=bible,
                     target_minutes=1, persist=True)
    assert ep is not None

    updated = store.read_bible(bible.series_id)
    names = [c.name for c in updated.characters]
    assert "Vesh" in names                       # new character promoted
    assert names.count("Vesh") == 1              # only once
    assert "ember" not in [n.lower() for n in names if n != "Ember"]  # dup skipped
    statuses = {c.name: c.status for c in updated.characters}
    assert statuses["Ash"] == "dead"             # death applied to status
    assert statuses["Ember"] == "alive"          # untouched
    assert any(f.statement == "The hoard was older than the volcano."
               for f in updated.world_facts)
    assert any(e["type"] == "step_complete" and e.get("stage") == "bible_update"
               for e in events)


def test_bible_update_lets_new_character_speak_next_episode(bible, tmp_path, monkeypatch):
    """A character introduced in ep1 is canon, so ep2 may give them a line."""
    import myAIstory.store as store
    monkeypatch.setattr(store, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(store, "SERIES_ROOT", tmp_path / "series")

    # ep1 kills Ash, so ep2 must not have Ash speak; Ember + the new canon Vesh do.
    ep2 = {
        "number": 2,
        "title": "Ep 2",
        "summary": "Ember meets the guard captain.",
        "beats": ["opening", "development", "resolution_or_hook"],
        "lines": [
            {"kind": "narration", "speaker": "narrator",
             "text": " ".join(["dragon"] + ["word"] * 79)},
            {"kind": "dialogue", "speaker": "Ember", "text": "Who guards this hoard?"},
            {"kind": "dialogue", "speaker": "Vesh", "text": "Halt, dragon."},
        ],
        "new_facts": [], "new_characters": [], "deaths": [],
    }

    events, emit = _capture()
    llm = ScriptedLLM({"episode_draft": [_episode_with_canon_updates(1), json.dumps(ep2)]})

    e1 = run_episode(bible.series_id, 1, llm, emit, bible=bible,
                     target_minutes=1, persist=True)
    assert e1 is not None
    # ep2 reuses the in-memory bible, now containing Vesh → speaker_verify passes.
    e2 = run_episode(bible.series_id, 2, llm, emit, bible=bible,
                     target_minutes=1, persist=True)
    assert e2 is not None
    assert "Vesh" in {l.speaker for l in e2.lines}


# --- speaker_salvage: pre-gate deterministic cleanup -------------------------

def _episode_with_undeclared_speaker(number: int = 1) -> str:
    """A valid episode that gives an invented incidental voice a line.

    'Blacksmith' is neither canon nor declared in new_characters — exactly the
    small-model failure mode that used to skip whole episodes.
    """
    base = json.loads(episode_json(number=number))
    base["lines"].append(
        {"kind": "dialogue", "speaker": "Blacksmith", "text": "Halt, dragon."}
    )
    return json.dumps(base)


def _episode_introduces_speaking_newcomer(number: int = 1) -> str:
    """A valid episode that DECLARES a newcomer and lets them speak at once."""
    base = json.loads(episode_json(number=number))
    base["new_characters"] = [{"name": "Vesh", "role": "guard", "status": "alive"}]
    base["lines"].append(
        {"kind": "dialogue", "speaker": "Vesh", "text": "Halt, dragon."}
    )
    return json.dumps(base)


def test_episode_salvages_undeclared_speaker(bible):
    """An invented incidental speaker is demoted to narrator, not skipped."""
    events, emit = _capture()
    llm = ScriptedLLM({"episode_draft": [_episode_with_undeclared_speaker(1)]})
    ep = run_episode("sid", 1, llm, emit, bible=bible, target_minutes=1, persist=False)
    assert ep is not None                       # NOT skipped
    assert len(llm.calls) == 1                  # salvaged on the first attempt
    # The Blacksmith line survives as narration, delivered by the narrator.
    salvaged = [l for l in ep.lines if l.text == "Halt, dragon."]
    assert salvaged and all(l.speaker == "narrator" and l.kind == "narration"
                            for l in salvaged)
    assert {l.speaker for l in ep.lines} <= {"narrator", "Ember", "Ash"}
    assert any(e["type"] == "step_complete" and e.get("stage") == "speaker_salvage"
               for e in events)


def test_episode_keeps_declared_speaker_and_promotes(bible, tmp_path, monkeypatch):
    """A speaker DECLARED in new_characters may speak this episode and is promoted."""
    import myAIstory.store as store
    monkeypatch.setattr(store, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(store, "SERIES_ROOT", tmp_path / "series")

    events, emit = _capture()
    llm = ScriptedLLM({"episode_draft": [_episode_introduces_speaking_newcomer(1)]})
    ep = run_episode(bible.series_id, 1, llm, emit, bible=bible,
                     target_minutes=1, persist=True)
    assert ep is not None
    assert len(llm.calls) == 1                  # accepted without a retry
    # Declared newcomer speaks in THIS episode — NOT demoted to narrator.
    assert "Vesh" in {l.speaker for l in ep.lines}
    # …and was promoted into canon by the verified bible_update stage.
    updated = store.read_bible(bible.series_id)
    assert "Vesh" in [c.name for c in updated.characters]
    # Nothing to salvage: a declared speaker triggers no demotion event.
    assert not any(e["type"] == "step_complete" and e.get("stage") == "speaker_salvage"
                   for e in events)


# --- run_series --------------------------------------------------------------

def test_series_end_to_end(seed):
    events, emit = _capture()
    llm = ScriptedLLM({
        "bible_draft": [frame_json()],
        "arc_beat": arc_beats(2),
        "episode_draft": [episode_json(1), episode_json(2)],
    })
    bible, episodes = run_series(seed.model_dump(), llm, emit,
                                 target_minutes=1, persist=False)
    assert bible is not None
    assert [e.number for e in episodes] == [1, 2]


def test_series_one_skip_continues(seed):
    events, emit = _capture()
    # Episode 1 fails all 3 attempts (skip); episode 2 succeeds.
    llm = ScriptedLLM({
        "bible_draft": [frame_json()],
        "arc_beat": arc_beats(2),
        "episode_draft": [bad_episode_json(1)] * 3 + [episode_json(2)],
    })
    bible, episodes = run_series(seed.model_dump(), llm, emit,
                                 target_minutes=1, max_retries=2, persist=False)
    assert bible is not None
    assert [e.number for e in episodes] == [2]  # ep1 skipped, run continued
    assert any(e["type"] == "skip" for e in events)
