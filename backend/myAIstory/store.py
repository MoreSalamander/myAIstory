"""Series storage (SPEC §5).

One directory per series under backend/data/series/. The bible is the source of
truth; episodes and (later) audio are verified, derived artifacts. events.ndjson
is the full ordered run log. No verification logic lives here — this module only
reads and writes what the gates have already approved.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from myAIstory.events import Sink
from myAIstory.schemas.models import Bible, Episode

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
SERIES_ROOT = DATA_ROOT / "series"


def slugify(title: str) -> str:
    """A filesystem-safe, deterministic series id from a title."""
    norm = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    norm = re.sub(r"[^a-zA-Z0-9]+", "-", norm).strip("-").lower()
    return norm or "series"


def series_dir(series_id: str) -> Path:
    return SERIES_ROOT / series_id


def ensure_series(series_id: str) -> Path:
    d = series_dir(series_id)
    (d / "episodes").mkdir(parents=True, exist_ok=True)
    (d / "audio").mkdir(parents=True, exist_ok=True)
    return d


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


# --- bible -------------------------------------------------------------------

def write_bible(bible: Bible) -> Path:
    ensure_series(bible.series_id)
    path = series_dir(bible.series_id) / "bible.json"
    _write_json(path, bible.model_dump())
    return path


def read_bible(series_id: str) -> Bible:
    path = series_dir(series_id) / "bible.json"
    return Bible.model_validate_json(path.read_text(encoding="utf-8"))


def bible_exists(series_id: str) -> bool:
    return (series_dir(series_id) / "bible.json").exists()


# --- episodes ----------------------------------------------------------------

def episode_path(series_id: str, number: int) -> Path:
    return series_dir(series_id) / "episodes" / f"{number:02d}.json"


def write_episode(series_id: str, episode: Episode) -> Path:
    ensure_series(series_id)
    path = episode_path(series_id, episode.number)
    _write_json(path, episode.model_dump())
    return path


def read_episode(series_id: str, number: int) -> Episode:
    return Episode.model_validate_json(
        episode_path(series_id, number).read_text(encoding="utf-8")
    )


def audio_path(series_id: str, number: int) -> Path:
    return series_dir(series_id) / "audio" / f"{number:02d}.wav"


def write_audio(series_id: str, number: int, wav_bytes: bytes) -> Path:
    """Persist a stitched episode track. Only verified episodes reach here."""
    ensure_series(series_id)
    path = audio_path(series_id, number)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(wav_bytes)
    return path


def prior_summaries(series_id: str, before_number: int) -> list[tuple[int, str]]:
    """Ordered (number, summary) for every persisted episode before `before_number`.

    This is the continuity context fed into the next episode's draft so the
    model can stay consistent without re-reading full prior episodes.
    """
    out: list[tuple[int, str]] = []
    for n in range(1, before_number):
        path = episode_path(series_id, n)
        if path.exists():
            ep = read_episode(series_id, n)
            out.append((ep.number, ep.summary))
    return out


# --- event log ---------------------------------------------------------------

def event_sink(series_id: str) -> Sink:
    """A sink that appends each event to the series' events.ndjson."""
    ensure_series(series_id)
    path = series_dir(series_id) / "events.ndjson"

    def _sink(event: dict) -> None:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    return _sink
