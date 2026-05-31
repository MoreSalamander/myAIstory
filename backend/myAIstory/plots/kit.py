"""Loader + deterministic selector for the plot grab bag.

The arc planner (Pipeline A's map step) asks the kit for ONE fitting plot shape
per episode, by arc position. Selection is a stable hash of
(series_id, episode, position) so re-running a series draws the same scaffolds —
reproducible casting of structure, mirroring the deterministic voice policy.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

# The arc positions a plot shape may fit. The planner maps episode 1 →
# "opening", the last episode → "finale", everything else → "middle".
POSITIONS = ("opening", "middle", "finale")


@dataclass(frozen=True)
class Plot:
    id: str
    name: str
    shape: str                          # theme-agnostic structural description
    fits: tuple[str, ...]               # subset of POSITIONS
    tags: tuple[str, ...] = field(default_factory=tuple)


def _stable_index(key: str, n: int) -> int:
    """A deterministic index in [0, n) from an arbitrary key (stable hash)."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest, 16) % n


class PlotKit:
    """Loads kit.json and selects a fitting plot shape per arc position."""

    def __init__(self, plots: list[Plot]) -> None:
        self.plots = plots

    @classmethod
    def load(cls, root: Path | str) -> "PlotKit":
        root = Path(root)
        manifest = root if root.suffix == ".json" else root / "kit.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        plots = [
            Plot(
                id=e["id"],
                name=e.get("name", e["id"]),
                shape=e["shape"],
                fits=tuple(e.get("fits", [])),
                tags=tuple(e.get("tags", [])),
            )
            for e in data.get("plots", [])
        ]
        return cls(plots)

    def for_position(self, position: str) -> list[Plot]:
        """Every plot shape that fits the given arc position (sorted by id)."""
        return sorted(
            (p for p in self.plots if position in p.fits), key=lambda p: p.id
        )

    def select(self, position: str, *, series_id: str, episode: int) -> Plot | None:
        """Deterministically pick ONE fitting plot for this beat, or None.

        Stable across re-runs of the same series: the same (series_id, episode,
        position) always yields the same shape, so structure is reproducible.
        """
        candidates = self.for_position(position)
        if not candidates:
            return None
        idx = _stable_index(f"{series_id}:{episode}:{position}", len(candidates))
        return candidates[idx]
