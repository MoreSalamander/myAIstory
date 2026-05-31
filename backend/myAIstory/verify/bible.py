"""bible_verify — the gate guarding the source of truth (SPEC §2).

Pure-Python. A drafted bible is only persisted if it is structurally valid AND
faithful to the seed: every seed character present by exact name, the theme
unchanged, the arc the right length, and no duplicate / colliding names.
"""

from __future__ import annotations

from myAIstory.schemas.models import ArcBeat, Bible, SeriesSeed
from myAIstory.verify.result import VerifyResult, parse


def verify_arc_beat(raw: object, episode: int) -> VerifyResult:
    """Gate one arc beat from the map step: valid shape, correct episode number.

    The arc is planned one beat at a time; each beat is an untrusted proposal
    checked here before it joins the bible. Pure-Python, like every gate.
    """
    result = VerifyResult(gate="arc_verify")

    result.add_check("schema")
    beat, viols = parse(ArcBeat, raw)
    if beat is None:
        result.violations.extend(viols)
        return result

    result.add_check("episode_match")
    if beat.episode != episode:
        result.fail(
            "arc_beat_episode_mismatch",
            f"beat is numbered {beat.episode}; expected episode {episode}",
            field="episode",
        )

    result.add_check("summary_nonempty")
    if not beat.summary.strip():
        result.fail(
            "arc_beat_empty_summary",
            f"episode {episode} beat has an empty summary",
            field="summary",
        )

    return result


def verify_bible(raw: object, seed: SeriesSeed, *, check_arc: bool = True) -> VerifyResult:
    """Validate a drafted bible against the seed it must honor."""
    result = VerifyResult(gate="bible_verify")

    result.add_check("schema")
    bible, viols = parse(Bible, raw)
    if bible is None:
        result.violations.extend(viols)
        return result

    canon_names = [c.name for c in bible.characters]
    canon_lower = {n.strip().lower() for n in canon_names}

    # Every seed character present by EXACT name (model may add, not drop/rename).
    result.add_check("seed_characters_present")
    for s in seed.characters:
        if s.name not in canon_names:
            result.fail(
                "missing_seed_character",
                f"seed character {s.name!r} is absent from the bible "
                "(seed characters may not be dropped or renamed)",
                field="characters",
            )

    # Theme unchanged from the seed.
    result.add_check("theme_match")
    if bible.theme.strip() != seed.theme.strip():
        result.fail(
            "theme_changed",
            f"bible theme {bible.theme!r} does not equal seed theme {seed.theme!r}",
            field="theme",
        )

    # episode_count carried through, and arc has exactly one beat per episode.
    result.add_check("episode_count_match")
    if bible.episode_count != seed.episode_count:
        result.fail(
            "episode_count_mismatch",
            f"bible episode_count {bible.episode_count} != seed {seed.episode_count}",
            field="episode_count",
        )

    # The arc is assembled from the per-episode map step; this final check
    # confirms the assembly is complete. Skipped when verifying the bare FRAME
    # (before the arc has been planned).
    if check_arc:
        result.add_check("arc_length")
        if len(bible.arc) != seed.episode_count:
            result.fail(
                "arc_length_mismatch",
                f"arc has {len(bible.arc)} beats; expected {seed.episode_count} "
                "(one per episode)",
                field="arc",
            )

    # No duplicate canon names (case-insensitive).
    result.add_check("no_duplicate_names")
    if len(canon_lower) != len(canon_names):
        result.fail(
            "duplicate_canon_name",
            "two canon characters share a name (case-insensitively)",
            field="characters",
        )

    # Alias collisions: an alias must not equal any other character's name or
    # alias, or every speaker resolution downstream becomes ambiguous.
    result.add_check("no_alias_collisions")
    owner: dict[str, str] = {n.strip().lower(): n for n in canon_names}
    for c in bible.characters:
        for alias in c.aliases:
            key = alias.strip().lower()
            if not key:
                continue
            if key in owner and owner[key] != c.name:
                result.fail(
                    "alias_collision",
                    f"alias {alias!r} of {c.name!r} collides with {owner[key]!r}",
                    field="characters",
                )
            else:
                owner.setdefault(key, c.name)

    return result
