"""PlotKit — the curated plot grab bag (pure-Python catalog + selector).

Like the sound library and voice policy, selection must be a deterministic
lookup: the same series re-runs to the same structural scaffolds.
"""

import json
from pathlib import Path

import pytest

from myAIstory.plots import Plot, PlotKit
from myAIstory.synth.prompts import build_arc_beat_prompt
from myAIstory.schemas.models import Bible, CanonCharacter

KIT = {
    "plots": [
        {"id": "open_a", "name": "Open A", "fits": ["opening"], "shape": "Open the world."},
        {"id": "mid_a", "name": "Mid A", "fits": ["middle"], "shape": "Raise the stakes."},
        {"id": "mid_b", "name": "Mid B", "fits": ["middle"], "shape": "Break a trust."},
        {"id": "end_a", "name": "End A", "fits": ["finale"], "shape": "Resolve it all."},
        {"id": "flex", "name": "Flex", "fits": ["opening", "finale"], "shape": "Flexible shape."},
    ]
}


@pytest.fixture
def kit(tmp_path: Path) -> PlotKit:
    (tmp_path / "kit.json").write_text(json.dumps(KIT), encoding="utf-8")
    return PlotKit.load(tmp_path)


def test_load_from_dir_and_file(tmp_path: Path):
    (tmp_path / "kit.json").write_text(json.dumps(KIT), encoding="utf-8")
    by_dir = PlotKit.load(tmp_path)
    by_file = PlotKit.load(tmp_path / "kit.json")
    assert len(by_dir.plots) == len(by_file.plots) == 5


def test_for_position_filters_and_sorts(kit: PlotKit):
    assert [p.id for p in kit.for_position("middle")] == ["mid_a", "mid_b"]
    # 'flex' fits both opening and finale.
    assert [p.id for p in kit.for_position("opening")] == ["flex", "open_a"]
    assert [p.id for p in kit.for_position("finale")] == ["end_a", "flex"]


def test_select_is_deterministic(kit: PlotKit):
    a = kit.select("middle", series_id="my-show", episode=2)
    b = kit.select("middle", series_id="my-show", episode=2)
    assert a is not None and a.id == b.id
    assert a.id in {"mid_a", "mid_b"}


def test_select_varies_by_episode_and_series(kit: PlotKit):
    picks = {kit.select("middle", series_id="s", episode=e).id for e in range(1, 12)}
    # Across many episodes both middle shapes get drawn (not stuck on one).
    assert picks == {"mid_a", "mid_b"}


def test_select_none_when_no_fit(kit: PlotKit):
    # A position with no catalog entries returns None (planner just omits it).
    empty = PlotKit([Plot(id="x", name="x", shape="s", fits=("middle",))])
    assert empty.select("opening", series_id="s", episode=1) is None


def test_real_shipped_kit_loads():
    root = Path(__file__).resolve().parent.parent / "data" / "plot_kit"
    if not (root / "kit.json").exists():
        pytest.skip("shipped plot kit not present")
    shipped = PlotKit.load(root)
    assert shipped.for_position("opening")
    assert shipped.for_position("middle")
    assert shipped.for_position("finale")


def test_plot_shape_appears_in_arc_prompt():
    bible = Bible(
        series_id="s", title="S", theme="dragons", tone="epic",
        characters=[CanonCharacter(name="Ember", role="lead")],
        world_facts=[], arc=[], episode_count=3,
    )
    with_shape = build_arc_beat_prompt(bible, 2, [(1, "x")], 3, plot_shape="Break a trust.")
    without = build_arc_beat_prompt(bible, 2, [(1, "x")], 3)
    assert "Break a trust." in with_shape
    assert "SUGGESTED BEAT SHAPE" in with_shape
    assert "SUGGESTED BEAT SHAPE" not in without
