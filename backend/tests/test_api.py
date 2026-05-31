"""HTTP surface (api.py) driven entirely offline.

A ScriptedLLM is injected via api.LLM_FACTORY and the data root is redirected
to a tmp dir, so the streaming generate endpoint and the read endpoints are
exercised with no Ollama and no real series directory.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from myAIstory import api, store
from myAIstory.synth import ScriptedLLM


def _bible_json() -> str:
    return json.dumps({
        "series_id": "x", "title": "The Ember Cycle", "theme": "dragons",
        "tone": "epic",
        "characters": [
            {"name": "Ember", "role": "protagonist", "status": "alive"},
            {"name": "Ash", "role": "rival", "status": "alive"},
        ],
        "world_facts": [], "arc": [{"episode": 1, "summary": "Ember finds the hoard."}],
        "episode_count": 1,
    })


def _episode_json() -> str:
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


SEED = {
    "title": "The Ember Cycle", "theme": "dragons", "tone": "epic",
    "characters": [{"name": "Ember", "role": "protagonist"}, {"name": "Ash", "role": "rival"}],
    "plot_direction": "Two dragons contest a hoard.",
    "episode_count": 1, "target_minutes": 1,
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(store, "SERIES_ROOT", tmp_path / "series")
    monkeypatch.setattr(api, "LLM_FACTORY", lambda: ScriptedLLM({
        "bible_draft": [_bible_json()],
        "episode_draft": [_episode_json()],
    }))
    return TestClient(api.app)


def _stream_events(client, body) -> list[dict]:
    with client.stream("POST", "/api/generate", json=body) as res:
        assert res.status_code == 200
        text = "".join(res.iter_text())
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_generate_streams_and_persists(client):
    events = _stream_events(client, {"seed": SEED, "minutes": 1, "voices": False})
    types = [e["type"] for e in events]
    assert "run_start" in types and "verify_pass" in types
    assert any(e["type"] == "done" and e.get("result") == "ok"
               and e.get("pipeline") == "episode" for e in events)
    assert "tts_line" not in types  # voices off

    # Persisted and now readable through the API.
    listing = client.get("/api/series").json()
    assert any(s["series_id"] == "the-ember-cycle" for s in listing)
    bible = client.get("/api/series/the-ember-cycle/bible").json()
    assert bible["theme"] == "dragons"
    ep = client.get("/api/series/the-ember-cycle/episode/1").json()
    assert ep["number"] == 1


def test_missing_series_404(client):
    assert client.get("/api/series/nope/bible").status_code == 404
    assert client.get("/api/series/nope/audio/1").status_code == 404


def test_index_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "my-" in res.text  # the frontend (or fallback) renders
