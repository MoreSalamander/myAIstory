"""voice_assign determinism + policy (pipeline/voice.py, SPEC §4)."""

from myAIstory.pipeline.voice import DEFAULT_NARRATOR_VOICE, assign_voices


def test_every_character_cast(bible):
    vm = assign_voices(bible)
    assert set(vm.by_character) == {"Ember", "Ash"}
    assert vm.narrator == DEFAULT_NARRATOR_VOICE


def test_casting_is_deterministic(bible):
    a = assign_voices(bible)
    b = assign_voices(bible)
    assert a.by_character == b.by_character  # same cast every run


def test_narrator_distinct_from_characters(bible):
    vm = assign_voices(bible)
    assert vm.narrator not in vm.by_character.values()


def test_explicit_voice_is_honored(bible):
    bible.characters[0].voice = "voice_05"  # Ember requests a specific voice
    vm = assign_voices(bible)
    assert vm.by_character["Ember"] == "voice_05"
