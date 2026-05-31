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
