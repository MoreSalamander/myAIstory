"""seed_validate gate (SPEC §1)."""

from myAIstory.verify import verify_seed


def test_valid_seed_passes(seed):
    result = verify_seed(seed)
    assert result.passed, str(result)
    assert "unique_character_names" in result.checks


def test_duplicate_character_name_fails(seed):
    raw = seed.model_dump()
    raw["characters"].append({"name": "ember"})  # case-insensitive clash
    result = verify_seed(raw)
    assert not result.passed
    assert any(v.code == "duplicate_character_name" for v in result.violations)


def test_unknown_voice_fails_when_registry_given(seed):
    raw = seed.model_dump()
    raw["characters"][0]["voice"] = "voice_does_not_exist"
    result = verify_seed(raw, available_voices={"voice_a", "voice_b"})
    assert not result.passed
    assert any(v.code == "unknown_voice" for v in result.violations)


def test_known_voice_passes_with_registry(seed):
    raw = seed.model_dump()
    raw["characters"][0]["voice"] = "voice_a"
    result = verify_seed(raw, available_voices={"voice_a", "voice_b"})
    assert result.passed, str(result)
    assert "voice_registry" in result.checks


def test_voice_check_skipped_without_registry(seed):
    raw = seed.model_dump()
    raw["characters"][0]["voice"] = "anything"
    result = verify_seed(raw)  # no registry → check skipped
    assert result.passed
    assert "voice_registry" not in result.checks


def test_out_of_range_episode_count_is_schema_violation(seed):
    raw = seed.model_dump()
    raw["episode_count"] = 999
    result = verify_seed(raw)
    assert not result.passed
    assert any(v.code.startswith("schema.") for v in result.violations)
