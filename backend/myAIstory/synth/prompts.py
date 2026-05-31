"""Prompt construction for the draft stages.

The prompts encode the human-owned constraints (CONSTITUTION "Explain") in the
form the model needs them: the schema to emit, the canon it must honor, and —
on a retry — the exact violations the verifier reported, so the next attempt is
corrective rather than a blind re-roll.
"""

from __future__ import annotations

from myAIstory.schemas.models import (
    BEAT_KINDS,
    REQUIRED_BEATS,
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
    return (
        "\n\nYour previous attempt was REJECTED by an automated verifier for "
        "these specific reasons. Fix every one of them in this attempt:\n"
        f"{bullets}\n{expand}"
    )


def build_bible_prompt(seed: SeriesSeed, feedback: list[str] | None = None) -> str:
    chars = "\n".join(
        f'  - {c.name}' + (f' (role: {c.role})' if c.role else "")
        for c in seed.characters
    )
    return f"""Create the series bible for this show.

TITLE: {seed.title}
THEME: {seed.theme}
TONE: {seed.tone or "unspecified"}
EPISODE COUNT: {seed.episode_count}
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
  "arc": [{{"episode": 1, "summary": "..."}}],
  "episode_count": {seed.episode_count}
}}

Rules:
- Keep THEME exactly as given: "{seed.theme}".
- Include every required character by their EXACT name.
- "arc" must have exactly {seed.episode_count} entries, one per episode.
{_feedback_block(feedback)}"""


def build_episode_prompt(
    bible: Bible,
    number: int,
    prior_summaries: list[tuple[int, str]],
    target_minutes: int,
    feedback: list[str] | None = None,
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
    low, high = target_minutes * 110, target_minutes * 170
    # ~28 spoken words per substantial line; anchor toward the high end because
    # small models chronically under-write. Floor the minimum at a few lines.
    min_lines = max(6, low // 28)
    return f"""Write episode {number} of "{bible.title}" (theme: {bible.theme}).

LENGTH IS A HARD REQUIREMENT — READ THIS FIRST.
This is a {target_minutes}-minute audio episode. It MUST contain {low}-{high}
total spoken words, and you should aim for the HIGH end (~{high} words). Plan on
writing at least {min_lines} substantial lines: narration in full paragraphs of
3-5 sentences, and dialogue exchanges of more than one short reply. A script
shorter than {low} words is AUTOMATICALLY REJECTED by a word-count checker and
you will have to redo the entire episode — so write generously and do not wrap
up early. Develop the scene, the setting, and the characters' inner states.

CANON CHARACTERS (only these may speak; dead characters may not speak):
{char_lines}

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
    {{"kind": "dialogue", "speaker": "EXACT character name", "text": "..."}}
  ],
  "new_facts": ["any new canon: a death, a reveal, a new character"]
}}

Rules:
- "beats" entries must come from: {", ".join(BEAT_KINDS)}; include at least {", ".join(REQUIRED_BEATS)}.
- Every dialogue "speaker" must be an EXACT canon name above; narration uses "narrator".
- LENGTH: {low}-{high} total spoken words (aim for ~{high}). This is enforced — do not under-write.
- Reference the theme "{bible.theme}" so the episode stays on-theme.
{_feedback_block(feedback)}"""
