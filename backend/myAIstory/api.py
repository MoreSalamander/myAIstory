"""FastAPI app: start verified runs and stream their events (ARCHITECTURE.md).

The pipeline is synchronous and emits through an EventEmitter; this module
bridges that to the wire. A run executes on a worker thread, its events land on
a queue, and the HTTP response streams them as NDJSON — the same event log the
CLI prints and store.event_sink persists, now also rendered live in a browser.

The LLM/TTS backends are built through module-level factories so tests can
drive the whole HTTP surface offline with a scripted model and no Ollama.
"""

from __future__ import annotations

import json
import queue
import threading
from pathlib import Path
from typing import Callable, Iterator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from myAIstory import store
from myAIstory.events import EventEmitter
from myAIstory.schemas.models import DEFAULT_MINUTES, SeriesSeed
from myAIstory.synth import OllamaClient
from myAIstory.synth.base import LLM
from myAIstory.pipeline.series import run_series

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
VOICES_DIR = store.DATA_ROOT / "voices"
KOKORO_DIR = store.DATA_ROOT / "voices_kokoro"
SOUND_LIBRARY_DIR = store.DATA_ROOT / "sound_library"
PLOT_KIT_DIR = store.DATA_ROOT / "plot_kit"

# Overridable seams (tests swap these for a ScriptedLLM and a temp data dir).
LLM_FACTORY: Callable[[], LLM] = OllamaClient


def build_tts(use_voices: bool, engine: str = "piper"):
    """Construct a TTS backend if voices are requested and installed.

    `engine` selects the local backend: "kokoro" (higher fidelity) or "piper".
    Returns None when voices are off or the chosen backend is unavailable, so
    the run cleanly falls back to a text-only (script) episode.
    """
    if not use_voices:
        return None
    if engine == "kokoro":
        from myAIstory.tts import KokoroError, KokoroTTS
        try:
            return KokoroTTS(KOKORO_DIR)
        except KokoroError:
            return None
    if not VOICES_DIR.is_dir():
        return None
    from myAIstory.tts import PiperError, PiperTTS
    try:
        return PiperTTS(VOICES_DIR)
    except PiperError:
        return None


def build_library(use_sound: bool):
    """Load the curated SoundLibrary if cues are requested and present."""
    if not use_sound or not (SOUND_LIBRARY_DIR / "library.json").exists():
        return None
    from myAIstory.sound import SoundLibrary
    try:
        return SoundLibrary.load(SOUND_LIBRARY_DIR)
    except Exception:
        return None


def build_kit():
    """Load the curated plot grab bag if present (auto-sampled by the arc planner)."""
    if not (PLOT_KIT_DIR / "kit.json").exists():
        return None
    from myAIstory.plots import PlotKit
    try:
        return PlotKit.load(PLOT_KIT_DIR)
    except Exception:
        return None


app = FastAPI(title="my-AI-story", description="A MoreSalamander StudioLabs production.")


# --- request model -----------------------------------------------------------

class GenerateRequest(BaseModel):
    seed: SeriesSeed
    minutes: Optional[int] = None
    episodes: Optional[int] = Field(default=None, ge=1)
    voices: bool = False
    engine: str = "piper"  # "piper" | "kokoro" (higher fidelity, local)
    sound: bool = False


# --- run + stream ------------------------------------------------------------

def _ndjson_run(req: GenerateRequest) -> Iterator[str]:
    """Run a series on a worker thread; yield each event as an NDJSON line."""
    events: "queue.Queue[Optional[dict]]" = queue.Queue()
    seed_raw = req.seed.model_dump()
    series_id = store.slugify(str(seed_raw.get("title", "series")))

    emit = EventEmitter([events.put, store.event_sink(series_id)])

    def worker() -> None:
        try:
            run_series(
                seed_raw, LLM_FACTORY(), emit,
                target_minutes=req.minutes,
                tts=build_tts(req.voices, req.engine),
                library=build_library(req.sound),
                kit=build_kit(),
                max_episodes=req.episodes,
            )
        except Exception as exc:  # surface as a final event, never a dropped stream
            emit.error("server", f"{type(exc).__name__}: {exc}")
        finally:
            events.put(None)  # sentinel

    threading.Thread(target=worker, daemon=True).start()

    while True:
        event = events.get()
        if event is None:
            break
        yield json.dumps(event, ensure_ascii=False) + "\n"


@app.post("/api/generate")
def generate(req: GenerateRequest) -> StreamingResponse:
    return StreamingResponse(_ndjson_run(req), media_type="application/x-ndjson")


# --- read existing series ----------------------------------------------------

@app.get("/api/series")
def list_series() -> list[dict]:
    out: list[dict] = []
    if not store.SERIES_ROOT.is_dir():
        return out
    for d in sorted(store.SERIES_ROOT.iterdir()):
        if not (d / "bible.json").exists():
            continue
        bible = store.read_bible(d.name)
        eps = sorted(
            int(p.stem) for p in (d / "episodes").glob("*.json")
        ) if (d / "episodes").is_dir() else []
        out.append({
            "series_id": bible.series_id,
            "title": bible.title,
            "theme": bible.theme,
            "episode_count": bible.episode_count,
            "episodes": eps,
        })
    return out


@app.get("/api/series/{series_id}/bible")
def get_bible(series_id: str) -> dict:
    if not store.bible_exists(series_id):
        raise HTTPException(404, "series not found")
    return store.read_bible(series_id).model_dump()


@app.get("/api/series/{series_id}/episode/{number}")
def get_episode(series_id: str, number: int) -> dict:
    if not store.episode_path(series_id, number).exists():
        raise HTTPException(404, "episode not found")
    return store.read_episode(series_id, number).model_dump()


@app.get("/api/series/{series_id}/audio/{number}")
def get_audio(series_id: str, number: int) -> FileResponse:
    path = store.audio_path(series_id, number)
    if not path.exists():
        raise HTTPException(404, "audio not found")
    return FileResponse(path, media_type="audio/wav", filename=f"{series_id}-{number:02d}.wav")


@app.get("/api/series/{series_id}/events")
def get_events(series_id: str) -> PlainTextResponse:
    path = store.series_dir(series_id) / "events.ndjson"
    if not path.exists():
        raise HTTPException(404, "no event log")
    return PlainTextResponse(path.read_text(encoding="utf-8"))


# --- frontend ----------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html = FRONTEND_DIR / "index.html"
    if not html.exists():
        return HTMLResponse("<h1>my-AI-story</h1><p>frontend not found</p>", status_code=200)
    return HTMLResponse(html.read_text(encoding="utf-8"))
