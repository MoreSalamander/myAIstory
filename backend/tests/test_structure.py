"""structure_verify gate (SPEC §3)."""

from myAIstory.schemas.models import Line
from myAIstory.verify import verify_structure

T = 1  # target_minutes used by the fixture → wide 60–240 word band


def test_valid_episode_passes(make_episode):
    result = verify_structure(make_episode(), expected_number=1, target_minutes=T)
    assert result.passed, str(result)


def test_wrong_number_fails(make_episode):
    result = verify_structure(make_episode(number=2), expected_number=1, target_minutes=T)
    assert not result.passed
    assert any(v.code == "episode_number_mismatch" for v in result.violations)


def test_missing_required_beat_fails(make_episode):
    ep = make_episode(beats=["opening", "development"])  # no resolution_or_hook
    result = verify_structure(ep, expected_number=1, target_minutes=T)
    assert not result.passed
    assert any(v.code == "missing_required_beat" for v in result.violations)


def test_unknown_beat_kind_fails(make_episode):
    ep = make_episode(beats=["opening", "development", "resolution_or_hook", "montage"])
    result = verify_structure(ep, expected_number=1, target_minutes=T)
    assert not result.passed
    assert any(v.code == "unknown_beat_kind" for v in result.violations)


def test_too_short_fails(make_episode):
    ep = make_episode(lines=[
        Line(kind="narration", speaker="narrator", text="A dragon stirs briefly."),
    ])
    result = verify_structure(ep, expected_number=1, target_minutes=T)
    assert not result.passed
    assert any(v.code == "too_short" for v in result.violations)


def test_too_long_fails(make_episode):
    ep = make_episode(lines=[
        Line(kind="narration", speaker="narrator", text=" ".join(["word"] * 400)),
    ])
    result = verify_structure(ep, expected_number=1, target_minutes=T)
    assert not result.passed
    assert any(v.code == "too_long" for v in result.violations)


def test_short_but_complete_episode_passes(make_episode):
    # The lenient floor: a 10-min episode with only ~200 spoken words is a
    # complete (if tight) episode, not a stub — it must NOT be rejected.
    # (Under the old 110 wpm floor this was a hard 1100-word reject.)
    ep = make_episode(lines=[
        Line(kind="narration", speaker="narrator", text=" ".join(["dragon"] * 200)),
    ])
    result = verify_structure(ep, expected_number=1, target_minutes=10)
    assert result.passed, str(result)


def test_stub_below_absolute_floor_fails(make_episode):
    # Even a long-runtime target rejects a true stub (under MIN_SPOKEN_WORDS).
    ep = make_episode(lines=[
        Line(kind="narration", speaker="narrator", text=" ".join(["dragon"] * 30)),
    ])
    result = verify_structure(ep, expected_number=1, target_minutes=10)
    assert not result.passed
    assert any(v.code == "too_short" for v in result.violations)


def test_empty_speech_text_fails(make_episode):
    ep = make_episode(lines=[
        Line(kind="narration", speaker="narrator", text=" ".join(["word"] * 140)),
        Line(kind="dialogue", speaker="Ember", text="   "),  # whitespace only
    ])
    result = verify_structure(ep, expected_number=1, target_minutes=T)
    assert not result.passed
    assert any(v.code == "empty_speech_text" for v in result.violations)


def test_cue_lines_do_not_count_toward_words(make_episode):
    # A phase-2 cue line carries no spoken text and must not affect the band.
    ep = make_episode(lines=[
        Line(kind="narration", speaker="narrator", text=" ".join(["word"] * 140)),
        Line(kind="sfx", cue="door_close"),
    ])
    result = verify_structure(ep, expected_number=1, target_minutes=T)
    assert result.passed, str(result)
