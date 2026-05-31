"""continuity_verify gate (SPEC §3)."""

from myAIstory.schemas.models import Line
from myAIstory.verify import verify_continuity


def test_valid_episode_passes(make_episode, bible):
    result = verify_continuity(make_episode(), bible)
    assert result.passed, str(result)


def test_alias_speaker_resolves(make_episode, bible):
    ep = make_episode(lines=[
        Line(kind="narration", speaker="narrator", text="A dragon stirs in the dark."),
        Line(kind="dialogue", speaker="The Emberling", text="The hoard is mine."),
    ])
    result = verify_continuity(ep, bible)
    assert result.passed, str(result)


def test_unresolved_speaker_fails(make_episode, bible):
    ep = make_episode(lines=[
        Line(kind="narration", speaker="narrator", text="A dragon stirs."),
        Line(kind="dialogue", speaker="Gandalf", text="You shall not pass."),
    ])
    result = verify_continuity(ep, bible)
    assert not result.passed
    assert any(v.code == "unresolved_speaker" for v in result.violations)


def test_dead_character_speaking_fails(make_episode, bible):
    bible.characters[1].status = "dead"  # Ash is dead
    ep = make_episode(lines=[
        Line(kind="narration", speaker="narrator", text="A dragon broods."),
        Line(kind="dialogue", speaker="Ash", text="I am not done yet."),
    ])
    result = verify_continuity(ep, bible)
    assert not result.passed
    assert any(v.code == "dead_character_speaking" for v in result.violations)


def test_dead_character_may_be_narrated(make_episode, bible):
    bible.characters[1].status = "dead"  # Ash is dead but only mentioned
    ep = make_episode(lines=[
        Line(kind="narration", speaker="narrator", text="Ash the dragon was gone."),
        Line(kind="dialogue", speaker="Ember", text="I will remember the wyrm."),
    ])
    result = verify_continuity(ep, bible)
    assert result.passed, str(result)


def test_theme_drift_fails(make_episode, bible):
    # No dragon marker anywhere in the spoken text → drift.
    plain = " ".join(["word"] * 30)
    ep = make_episode(lines=[
        Line(kind="narration", speaker="narrator", text=plain),
        Line(kind="dialogue", speaker="Ember", text="Hello there friend."),
    ])
    result = verify_continuity(ep, bible)
    assert not result.passed
    assert any(v.code == "theme_drift" for v in result.violations)


def test_free_text_theme_skips_marker_check(make_episode, bible):
    bible.theme = "interpersonal melodrama"  # not in the marker map
    plain = " ".join(["word"] * 30)
    ep = make_episode(lines=[Line(kind="narration", speaker="narrator", text=plain)])
    result = verify_continuity(ep, bible)
    assert result.passed, str(result)
    assert "theme_marker_present" not in result.checks
