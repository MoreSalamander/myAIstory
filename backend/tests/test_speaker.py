"""speaker_verify gate (SPEC §3)."""

from myAIstory.schemas.models import Line
from myAIstory.verify import verify_speaker


def test_valid_episode_passes(make_episode, voice_map, bible):
    result = verify_speaker(make_episode(), voice_map, bible)
    assert result.passed, str(result)


def test_narrator_always_voiced(make_episode, voice_map):
    ep = make_episode(lines=[
        Line(kind="narration", speaker="narrator", text="A dragon stirs."),
    ])
    result = verify_speaker(ep, voice_map)  # no bible needed for narrator
    assert result.passed, str(result)


def test_speaker_missing_from_voice_map_fails(make_episode, voice_map, bible):
    voice_map.by_character.pop("Ash")  # Ash now has no voice
    result = verify_speaker(make_episode(), voice_map, bible)
    assert not result.passed
    assert any(v.code == "no_voice_for_speaker" for v in result.violations)


def test_alias_resolves_to_voiced_canon(make_episode, voice_map, bible):
    ep = make_episode(lines=[
        Line(kind="narration", speaker="narrator", text="A dragon stirs."),
        Line(kind="dialogue", speaker="The Emberling", text="Mine."),  # alias of Ember
    ])
    result = verify_speaker(ep, voice_map, bible)
    assert result.passed, str(result)


def test_speakerless_line_fails(make_episode, voice_map):
    ep = make_episode(lines=[
        Line(kind="dialogue", speaker=None, text="Who said that?"),
    ])
    result = verify_speaker(ep, voice_map)
    assert not result.passed
    assert any(v.code == "unvoiced_line" for v in result.violations)


def test_cue_lines_need_no_voice(make_episode, voice_map):
    ep = make_episode(lines=[
        Line(kind="narration", speaker="narrator", text="Quiet."),
        Line(kind="music", cue="tension_build", under=True),
    ])
    result = verify_speaker(ep, voice_map)
    assert result.passed, str(result)
