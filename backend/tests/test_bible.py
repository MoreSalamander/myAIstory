"""bible_verify gate (SPEC §2)."""

from myAIstory.verify import verify_bible


def test_valid_bible_passes(bible, seed):
    result = verify_bible(bible, seed)
    assert result.passed, str(result)


def test_missing_seed_character_fails(bible, seed):
    raw = bible.model_dump()
    raw["characters"] = [c for c in raw["characters"] if c["name"] != "Ash"]
    result = verify_bible(raw, seed)
    assert not result.passed
    assert any(v.code == "missing_seed_character" for v in result.violations)


def test_renamed_seed_character_fails(bible, seed):
    raw = bible.model_dump()
    raw["characters"][1]["name"] = "Cinder"  # Ash renamed
    result = verify_bible(raw, seed)
    assert not result.passed
    assert any(v.code == "missing_seed_character" for v in result.violations)


def test_theme_change_fails(bible, seed):
    raw = bible.model_dump()
    raw["theme"] = "vampires"
    result = verify_bible(raw, seed)
    assert not result.passed
    assert any(v.code == "theme_changed" for v in result.violations)


def test_arc_length_mismatch_fails(bible, seed):
    raw = bible.model_dump()
    raw["arc"] = raw["arc"][:1]  # only one beat for a 2-episode series
    result = verify_bible(raw, seed)
    assert not result.passed
    assert any(v.code == "arc_length_mismatch" for v in result.violations)


def test_episode_count_mismatch_fails(bible, seed):
    raw = bible.model_dump()
    raw["episode_count"] = 5
    result = verify_bible(raw, seed)
    assert not result.passed
    assert any(v.code == "episode_count_mismatch" for v in result.violations)


def test_alias_collision_fails(bible, seed):
    raw = bible.model_dump()
    raw["characters"][1]["aliases"] = ["Ember"]  # Ash aliased to Ember's name
    result = verify_bible(raw, seed)
    assert not result.passed
    assert any(v.code == "alias_collision" for v in result.violations)


def test_model_may_add_characters(bible, seed):
    raw = bible.model_dump()
    raw["characters"].append({"name": "Soot", "role": "mentor"})
    result = verify_bible(raw, seed)
    assert result.passed, str(result)  # adding is allowed; dropping/renaming is not
