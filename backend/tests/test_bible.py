"""bible_verify gate (SPEC §2)."""

from myAIstory.verify import verify_arc_beat, verify_bible


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


# --- frame mode: arc_length is skipped while the arc is still being planned --

def test_frame_with_empty_arc_passes_when_arc_unchecked(bible, seed):
    raw = bible.model_dump()
    raw["arc"] = []  # a frame has no arc yet
    assert not verify_bible(raw, seed).passed                 # full gate rejects
    assert verify_bible(raw, seed, check_arc=False).passed     # frame gate accepts


def test_frame_mode_still_enforces_the_other_checks(bible, seed):
    raw = bible.model_dump()
    raw["arc"] = []
    raw["theme"] = "vampires"  # theme drift must still fail in frame mode
    result = verify_bible(raw, seed, check_arc=False)
    assert not result.passed
    assert any(v.code == "theme_changed" for v in result.violations)


# --- arc_verify: one beat from the map step ---------------------------------

def test_arc_beat_valid_passes():
    assert verify_arc_beat({"episode": 3, "summary": "Ash strikes."}, 3).passed


def test_arc_beat_wrong_episode_fails():
    result = verify_arc_beat({"episode": 2, "summary": "..."}, 3)
    assert not result.passed
    assert any(v.code == "arc_beat_episode_mismatch" for v in result.violations)


def test_arc_beat_empty_summary_fails():
    result = verify_arc_beat({"episode": 1, "summary": "   "}, 1)
    assert not result.passed
    assert any(v.code == "arc_beat_empty_summary" for v in result.violations)


def test_arc_beat_malformed_fails():
    result = verify_arc_beat({"episode": "one"}, 1)  # bad type, no summary
    assert not result.passed
    assert "schema" in result.checks
