"""SoundLibrary — the curated cue registry (SPEC §4b).

The asset catalog the model's cue tags are checked against. Like the verify/
package and the available-voices registry, resolution here is a pure lookup —
no LLM, no network. A cue the model emits is an untrusted proposal; it only
becomes audio if its tag (or a known alias) is in this human-owned manifest.
"""

from __future__ import annotations

import json
import wave
from dataclasses import dataclass, field
from pathlib import Path

from myAIstory.tts.base import Clip


@dataclass(frozen=True)
class Asset:
    tag: str
    kind: str           # sfx | ambience | music
    file: str           # path relative to the library root
    gain_db: float = 0.0
    loop: bool = False
    aliases: list[str] = field(default_factory=list)


class SoundLibrary:
    """Loads library.json and resolves cue tags (and aliases) to assets."""

    def __init__(self, root: Path, assets: list[Asset]) -> None:
        self.root = Path(root)
        self.assets = assets
        self._index: dict[str, Asset] = {}
        for a in assets:
            self._index[a.tag.strip().lower()] = a
            for alias in a.aliases:
                self._index.setdefault(alias.strip().lower(), a)

    @classmethod
    def load(cls, root: Path | str) -> "SoundLibrary":
        root = Path(root)
        manifest = root / "library.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assets = [
            Asset(
                tag=e["tag"], kind=e["kind"], file=e["file"],
                gain_db=float(e.get("gain_db", 0.0)),
                loop=bool(e.get("loop", False)),
                aliases=list(e.get("aliases", [])),
            )
            for e in data.get("assets", [])
        ]
        return cls(root, assets)

    @property
    def tags(self) -> list[str]:
        return [a.tag for a in self.assets]

    def resolve(self, cue: str | None) -> Asset | None:
        """The cue tag (or alias) → Asset, or None if it isn't in the catalog."""
        if not cue:
            return None
        return self._index.get(cue.strip().lower())

    def load_clip(self, asset: Asset) -> Clip:
        """Read an asset file into a Clip (mono PCM)."""
        path = self.root / asset.file
        with wave.open(str(path), "rb") as w:
            frames = w.readframes(w.getnframes())
            return Clip(
                frames=frames,
                sample_rate=w.getframerate(),
                sample_width=w.getsampwidth(),
                channels=w.getnchannels(),
            )
