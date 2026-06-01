"""Prompt construction for the draft stages.

The prompts encode the human-owned constraints (CONSTITUTION "Explain") in the
form the model needs them: the schema to emit, the canon it must honor, and —
on a retry — the exact violations the verifier reported, so the next attempt is
corrective rather than a blind re-roll.
"""

from __future__ import annotations

from myAIstory.schemas.models import (
    BEAT_KINDS,
    MIN_SPOKEN_WORDS,
    REQUIRED_BEATS,
    WPM_AIM,
    WPM_MIN,
    Bible,
    SeriesSeed,
)

_JSON_ONLY = (
    "Respond with ONE valid JSON object and nothing else — no prose, no "
    "markdown fences, no commentary before or after."
)

BIBLE_SYSTEM = (
    "You are a series bible architect for a serialized audio fiction studio. "
    "You invent consistent characters and worlds that downstream episodes must "
    "never contradict. You follow the requested JSON schema exactly. " + _JSON_ONLY
)

EPISODE_SYSTEM = (
    "You are a serialized-fiction writer. You write one episode at a time, "
    "staying strictly consistent with the established series bible and prior "
    "episodes. Dialogue is attributed to a named speaker; narration is "
    "attributed to \"narrator\". You follow the requested JSON schema exactly. "
    + _JSON_ONLY
)


def _feedback_block(feedback: list[str] | None) -> str:
    if not feedback:
        return ""
    bullets = "\n".join(f"- {v}" for v in feedback)
    too_short = any("too_short" in v or "below the" in v for v in feedback)
    expand = (
        "\nYou wrote too little last time. This attempt must be SUBSTANTIALLY "
        "longer — add more lines and lengthen existing ones; do not just tweak.\n"
        if too_short else ""
    )
    bad_speaker = any(
        "unresolved_speaker" in v or "no_voice_for_speaker" in v
        or "is neither" in v for v in feedback
    )
    fix_speaker = (
        "\nYou attributed a line to a speaker who is NOT a canon character. Every "
        "dialogue 'speaker' must be one of the EXACT canon names listed above; for "
        "any incidental or background voice (a guard, a vendor, a crowd) use "
        '"narrator" instead of inventing a name. If you need a recurring NEW '
        "character, put them in \"new_characters\" — do not give an unlisted name a "
        "line.\n" if bad_speaker else ""
    )
    return (
        "\n\nYour previous attempt was REJECTED by an automated verifier for "
        "these specific reasons. Fix every one of them in this attempt:\n"
        f"{bullets}\n{expand}{fix_speaker}"
    )


def build_bible_prompt(seed: SeriesSeed, feedback: list[str] | None = None) -> str:
    """The bible FRAME: characters and world, but NOT the per-episode arc.

    The arc is planned one beat at a time afterwards (build_arc_beat_prompt) —
    small models reliably write one good beat per call but collapse when asked
    to emit all N at once. So this prompt deliberately leaves "arc" empty.
    """
    chars = "\n".join(
        f'  - {c.name}' + (f' (role: {c.role})' if c.role else "")
        for c in seed.characters
    )
    n = seed.episode_count
    return f"""Create the series bible FRAME for this show — the cast and world.
Do NOT write the episode arc here; it is planned separately, one episode at a
time, in a later step. Leave "arc" as an empty list.

TITLE: {seed.title}
THEME: {seed.theme}
TONE: {seed.tone or "unspecified"}
EPISODE COUNT: {n}
LOOSE PLOT DIRECTION: {seed.plot_direction or "(none given — invent a coherent arc)"}

REQUIRED CHARACTERS (use these EXACT names, you may add more):
{chars}

Emit JSON with this shape:
{{
  "series_id": "{seed.title.lower().replace(' ', '-')}",
  "title": "{seed.title}",
  "theme": "{seed.theme}",
  "tone": "{seed.tone or ''}",
  "characters": [
    {{"name": "EXACT name", "aliases": [], "role": "...", "status": "alive", "facts": ["..."]}}
  ],
  "world_facts": [{{"id": "wf1", "statement": "...", "established_in_episode": null}}],
  "arc": [],
  "episode_count": {n}
}}

Rules:
- Keep THEME exactly as given: "{seed.theme}".
- Include every required character by their EXACT name.
- Leave "arc" empty — do NOT invent episode beats here.
{_feedback_block(feedback)}"""


def _plot_block(plot_shape: str | None) -> str:
    if not plot_shape:
        return ""
    return (
        "\nSUGGESTED BEAT SHAPE (a classic structure to ADAPT — make it specific "
        "to THIS cast and theme; do not name or quote it literally, just let it "
        f"guide what happens):\n  {plot_shape}\n"
    )


def build_arc_beat_prompt(
    bible: Bible,
    episode: int,
    prior_beats: list[tuple[int, str]],
    total: int,
    feedback: list[str] | None = None,
    plot_shape: str | None = None,
) -> str:
    """Plan ONE arc beat (episode K) given the frame and every prior beat.

    This is the map step (advisor-style): one focused call writes the single
    beat for episode K, grounded in the established cast/world and the arc so
    far, so the through-line stays coherent without asking the model to hold all
    {total} beats in one response. ``plot_shape`` is an optional theme-agnostic
    scaffold drawn from the curated plot kit for the model to specialize.
    """
    char_lines = "\n".join(
        f'  - {c.name}' + (f' (role: {c.role})' if c.role else "")
        for c in bible.characters
    ) or "  (none)"
    so_far = (
        "\n".join(f"  Episode {n}: {s}" for n, s in prior_beats)
        or "  (none yet — this is the first beat)"
    )
    where = (
        "the OPENING beat — establish the situation" if episode == 1
        else "the FINALE — resolve the series' through-line" if episode == total
        else f"a MIDDLE beat — escalate toward the finale at episode {total}"
    )
    return f"""Plan the arc beat for ONE episode of "{bible.title}" (theme: {bible.theme}).

This is episode {episode} of {total} — {where}.

CAST / WORLD (established; stay consistent, do not contradict):
{char_lines}

ARC SO FAR (the beats already planned — continue from here, do not repeat them):
{so_far}
{_plot_block(plot_shape)}
Write a single 1-2 sentence beat that advances the story for episode {episode}.

Emit JSON with EXACTLY this shape (one object, nothing else):
{{"episode": {episode}, "summary": "..."}}

Rules:
- "episode" MUST be exactly {episode}.
- "summary" is 1-2 sentences, concrete, and moves the arc forward from the beats above.
- Reference the theme "{bible.theme}".
{_feedback_block(feedback)}"""


def _cue_block(cue_tags: list[str] | None) -> str:
    if not cue_tags:
        return ""
    tags = ", ".join(cue_tags)
    return f"""

OPTIONAL SOUND CUES (enhancement only — never required):
You MAY interleave sound cues between speech lines for atmosphere. A cue is a
line of the form {{"kind": "sfx"|"ambience"|"music", "cue": "TAG", "under": true|false}}.
- Use ONLY these tags (anything else is silently dropped): {tags}
- "sfx" are one-shot moments (a door, a clash); "ambience"/"music" are beds —
  set "under": true so they play quietly beneath the following narration.
- Cues carry no "speaker"/"text". They do NOT count toward the word total.
- When in doubt, omit them. Sound must never distort the story."""


def build_episode_prompt(
    bible: Bible,
    number: int,
    prior_summaries: list[tuple[int, str]],
    target_minutes: int,
    feedback: list[str] | None = None,
    cue_tags: list[str] | None = None,
) -> str:
    char_lines = "\n".join(
        f'  - {c.name} ({c.status})' + (f', aka {", ".join(c.aliases)}' if c.aliases else "")
        for c in bible.characters
    )
    arc_beat = next((b.summary for b in bible.arc if b.episode == number), "")
    recap = (
        "\n".join(f"  Episode {n}: {s}" for n, s in prior_summaries)
        or "  (this is the first episode)"
    )
    aim = target_minutes * WPM_AIM
    floor = max(MIN_SPOKEN_WORDS, target_minutes * WPM_MIN)
    # ~28 spoken words per substantial line; anchor toward the aim because
    # small models chronically under-write. Floor the minimum at a few lines.
    min_lines = max(6, aim // 28)
    return f"""Write episode {number} of "{bible.title}" (theme: {bible.theme}).

LENGTH — WRITE A FULL EPISODE, READ THIS FIRST.
This is a {target_minutes}-minute audio episode. Aim for about {aim} total spoken
words so the narration fills the runtime — plan on at least {min_lines} substantial
lines: narration in full paragraphs of 3-5 sentences, and dialogue exchanges of
more than one short reply. Write generously and do not wrap up early — develop the
scene, the setting, and the characters' inner states. There is NO upper word limit
to worry about and no penalty for falling a little short of the aim; let the scene
run as long as the beat needs. The only hard rule is that a tiny stub (under {floor}
spoken words) is rejected — so always write a complete, fleshed-out episode.

CANON CHARACTERS — THE ONLY NAMES THAT MAY SPEAK:
{char_lines}
A dialogue line's "speaker" MUST be one of these EXACT names, or "narrator".
This is strictly enforced: a line attributed to any other name is REJECTED and
you redo the whole episode. For ANY incidental or background voice — a guard, a
vendor, a messenger, a crowd — DO NOT invent a name; either attribute the line to
"narrator" (e.g. narrate what they say) or describe them in narration. A dead
character may not speak.

If the story genuinely needs a NEW recurring character, introduce them in
narration and list them under "new_characters" — they then become canon and may
speak in LATER episodes (not this one). Likewise, if a canon character dies, list
their exact name under "deaths".

STORY SO FAR:
{recap}

THIS EPISODE'S ARC BEAT:
  {arc_beat or "(advance the story coherently)"}

Emit JSON with this shape:
{{
  "number": {number},
  "title": "...",
  "summary": "1-2 sentence recap for continuity",
  "beats": ["opening", "development", "resolution_or_hook"],
  "lines": [
    {{"kind": "narration", "speaker": "narrator", "text": "..."}},
    {{"kind": "dialogue", "speaker": "EXACT canon name or narrator", "text": "..."}}
  ],
  "new_facts": ["any new world canon: a reveal, an event, a place"],
  "new_characters": [{{"name": "New Name", "role": "...", "status": "alive"}}],
  "deaths": ["exact canon name who died this episode"]
}}
("new_characters" and "deaths" are usually empty — only fill them when the story
actually introduces or kills someone.)

Rules:
- "beats" entries must come from: {", ".join(BEAT_KINDS)}; include at least {", ".join(REQUIRED_BEATS)}.
- Every dialogue "speaker" must be an EXACT canon name above, or "narrator". NEVER invent a speaker name — incidental voices use "narrator".
- LENGTH: aim for ~{aim} total spoken words (a full {target_minutes}-min episode); never write a stub under {floor} words.
- Reference the theme "{bible.theme}" so the episode stays on-theme.{_cue_block(cue_tags)}
{_feedback_block(feedback)}"""
