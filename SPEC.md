# my-AI-story — Spec

> The schemas and the acceptance criteria. This is the contract each
> pipeline stage produces against and each verifier checks against. If a
> verifier and this document disagree, the verifier is wrong.

All schemas are expressed below as field tables; the canonical
implementation lives in `backend/myAIstory/schemas/` as Pydantic models. The
tables here are authoritative for *intent*; the Pydantic models are
authoritative for *exact types* and must match these tables.

---

## 1. SeriesSeed (human-owned input)

The user's input. Validated by `seed_validate` before anything else runs.

| Field | Type | Rule |
|---|---|---|
| `title` | str | non-empty, ≤ 120 chars |
| `theme` | str | non-empty; free-text, but a curated set (`dragons`, `werewolves`, `vampires`, `space-opera`, `noir`, …) is offered in the UI |
| `characters` | list[CharacterSeed] | 1–12 entries; names unique (case-insensitive) |
| `plot_direction` | str | loose, free-text; ≤ 2000 chars; may be empty |
| `episode_count` | int | 1–50 |
| `tone` | str | optional; e.g. `dark`, `comedic`, `epic`, `cozy` |
| `target_minutes` | int | optional per-episode audio target; 1–30; default 5 |

**CharacterSeed**

| Field | Type | Rule |
|---|---|---|
| `name` | str | non-empty, unique within the series |
| `role` | str | optional hint, e.g. `protagonist`, `rival`, `mentor` |
| `voice` | str | optional; a voice id from the available TTS voices. If omitted, assigned deterministically at `voice_assign` |

**`seed_validate` acceptance criteria** (pure-Python):
- title non-empty; `episode_count` in 1–50; `target_minutes` in 1–30.
- ≥ 1 character; all character names unique case-insensitively.
- every supplied `voice` id exists in the available-voices registry.

---

## 2. Bible (the source of truth)

Produced by `bible_draft`, gated by `bible_verify`, persisted as
`bible.json`. Updated only through the verified `bible_update` stage.

| Field | Type | Rule |
|---|---|---|
| `series_id` | str | slug, generated |
| `title` | str | copied from seed |
| `theme` | str | copied from seed |
| `tone` | str | from seed or model-proposed, then human-visible |
| `characters` | list[CanonCharacter] | superset of seed characters; model may add, but seed characters must all be present and unchanged in name |
| `world_facts` | list[WorldFact] | established truths the story must not contradict |
| `arc` | list[ArcBeat] | high-level skeleton, one entry per planned episode |
| `episode_count` | int | from seed |
| `created_at` / `updated_at` | iso8601 | |

**CanonCharacter**

| Field | Type | Rule |
|---|---|---|
| `name` | str | unique; seed names immutable |
| `aliases` | list[str] | optional; alternate names that resolve to this character |
| `role` | str | |
| `voice` | str | resolved TTS voice id (set by `voice_assign` at latest) |
| `status` | str | `alive` / `dead` / `unknown`; starts `alive`; only `bible_update` may change it |
| `facts` | list[str] | per-character canon (relationships, traits) |

**WorldFact**: `{ id: str, statement: str, established_in_episode: int|null }`

**ArcBeat**: `{ episode: int, summary: str }`

**`bible_verify` acceptance criteria** (pure-Python):
- schema valid.
- **every seed character present by exact name** (model may add but not
  drop or rename seed characters).
- `theme` equals seed theme.
- `arc` length == `episode_count`.
- no duplicate character names / alias collisions.

---

## 3. Episode

Produced by `episode_draft`, gated by three verifiers, persisted as
`episodes/NN.json`.

| Field | Type | Rule |
|---|---|---|
| `number` | int | 1-based; matches filename `NN` |
| `title` | str | non-empty |
| `summary` | str | 1–3 sentence recap; fed into later episodes' `context_load` |
| `beats` | list[str] | the episode's structural beats; must cover the required beat kinds (below) |
| `lines` | list[Line] | ordered narration + dialogue |
| `new_facts` | list[str] | canon proposed for `bible_update` (deaths, reveals, new characters) |

**Line** (the timeline unit — speech *or*, in phase 2, an audio cue)

| Field | Type | Rule |
|---|---|---|
| `speaker` | str | `"narrator"` or a canon character name/alias (speech kinds only) |
| `text` | str | the words spoken (speech kinds only; non-empty) |
| `kind` | str | one of `narration`, `dialogue` (v1) — or `sfx`, `ambience`, `music` (phase 2) |
| `cue` | str\|null | **phase 2.** For cue kinds: an asset tag (e.g. `door_close`, `forest`, `tension_build`) that must resolve in the sound library. Null for speech kinds |
| `under` | bool | **phase 2.** For `ambience`/`music`: if true, this bed plays *underneath* following speech lines (ducked) until the next bed cue. Default false |

In v1 every line is `narration` or `dialogue`. The `cue`/`under` fields
exist in the schema from day one so phase 2 adds no breaking change.

**Required beat kinds** (structure): each episode must contain at least an
`opening`, a `development`, and a `resolution_or_hook` beat. (Exact beat
taxonomy lives in the schema module; this is the minimum.)

### Verifier acceptance criteria (the three gates)

**`continuity_verify`** (pure-Python, blocking):
- every `speaker` resolves to a canon character (by name or alias) or is
  `narrator`.
- no line references a character as alive whose `status` is `dead` in the
  bible (basic contradiction check against `world_facts` and character
  `status`).
- theme-marker check: episode does not contradict `theme` (heuristic /
  keyword-fenced, deterministic — not an LLM).
- no seed character renamed.

**`structure_verify`** (pure-Python, blocking):
- schema valid; `number` matches expected episode index.
- required beat kinds all present.
- total spoken text length within bounds derived from `target_minutes`
  (word-count band, deterministic).
- `lines` non-empty; every line `text` non-empty.

**`speaker_verify`** (pure-Python, blocking):
- **every** speech line's `speaker` maps to a resolved TTS voice (after
  `voice_assign`) — no unattributable line may reach TTS.

**`cue_verify`** (pure-Python — **phase 2**, *non-blocking*):
- for every cue line (`sfx`/`ambience`/`music`), its `cue` tag resolves to
  an asset in the sound library registry (by tag or alias).
- an **unresolved cue is dropped** (the line is removed and a `skip` event
  logged) — it does **not** fail the episode. Rationale: a missing
  footstep sound must never block a verified story from being narrated.
  This is the one deliberately *non-blocking* gate; speech gates stay
  blocking.
- `under` beds must be balanced (a bed that opens is allowed to run to
  end-of-episode; overlapping beds of the same kind are collapsed to the
  most recent).

Any blocking-gate failure → `verify_fail` event → bounded retry (default 2) with the
violation fed back into `episode_draft` → on exhaustion, `skip` + log.
**No failed episode is ever persisted or sent to TTS.**

---

## 4. VoiceMap

Resolved by `voice_assign`. Not user-authored as a whole; derived from the
voice policy + any per-character `voice` choices in the seed.

| Field | Type | Rule |
|---|---|---|
| `narrator` | str | a TTS voice id reserved for narration |
| `by_character` | dict[str, str] | canon character name → TTS voice id |

**Voice policy** (deterministic assignment):
- `narrator` gets a dedicated voice, distinct from all character voices
  where the voice registry allows.
- a character with a seed-specified `voice` keeps it.
- remaining characters are assigned from the available-voices registry
  **deterministically** (stable hash of character name → voice index),
  so re-running a series yields the same casting.
- if there are more characters than distinct voices, voices are reused but
  the assignment remains deterministic and recorded in the bible.

**Available-voices registry**: provided by the active TTS backend through
the pluggable interface (`tts/`), as a list of `{id, label, sample?}`.

---

## 4b. SoundLibrary (phase 2)

The asset registry the LLM's cues are verified against. It is **human-owned
and curated**, not model-generated — the model may only reference tags that
already exist here. This is the cue equivalent of the available-voices
registry: cues are untrusted proposals checked against a fixed catalog.

A `sound_library/library.json` manifest catalogs every available asset:

| Field | Type | Rule |
|---|---|---|
| `tag` | str | unique cue id, e.g. `door_close`, `footsteps_gravel` |
| `kind` | str | `sfx`, `ambience`, or `music` |
| `aliases` | list[str] | alternate tags the model might emit that resolve here |
| `file` | str | path under `sound_library/` to the audio asset |
| `gain_db` | float | default mix level relative to speech (negative = quieter) |
| `loop` | bool | ambience/music beds loop to fill their span; sfx are one-shot |

**Sourcing**: v-phase-2 ships a small curated set of free-licensed clips
(footsteps, doors, rustling, traffic; a few mood beds — tension, calm,
triumph). Generative audio (MusicGen/AudioGen) is a *later* option behind
the same manifest interface; the pipeline never cares how an asset was
made, only that its tag resolves.

**Mix policy** (deterministic, in the `stitch`/mix stage):
- speech is the reference track; cue `gain_db` is relative to it.
- `under` beds are **ducked** beneath speech (additional fixed
  attenuation) and fade in/out at their span boundaries.
- one-shot `sfx` are placed at their line's position in the timeline.

---

## 5. Storage layout (per series)

```
backend/data/series/<series_id>/
  bible.json            # source of truth (schema §2)
  episodes/
    01.json … NN.json   # verified episodes (schema §3)
  audio/
    01.wav … NN.wav     # stitched narration (+ mixed cues in phase 2)
  events.ndjson         # full ordered run log
```

The curated asset catalog lives **outside** any single series, shared
across all of them:

```
backend/data/sound_library/
  library.json          # the SoundLibrary manifest (§4b)
  sfx/ ambience/ music/ # the asset files
```

A series is reproducible from `bible.json` + the seed: re-running episode
generation against the same bible yields deterministically-cast audio,
though prose will vary with model sampling.

---

## 6. Scope by phase

**v1 — voices only.** Narration + dialogue, per-character TTS, sequential
stitch. The `cue`/`under` schema fields exist but are unused; no
`cue_verify`, no mixing. Proves the core story+continuity+voice loop.

**Phase 2 — sound design.** SFX, ambience, and mood/build-up music via the
SoundLibrary (§4b), the `cue_verify` gate, and a timeline-mixing stitch
stage (ducking, fades, one-shot placement). Designed-for from day one — no
schema break, no pipeline rewrite, just new stages + the asset catalog.

**Out of scope entirely (both phases):**

- No cloud TTS / cloud LLM. Local-only (per `CONSTITUTION.md`).
- No multi-user accounts, no auth. Single local operator.
- No branching/interactive stories — linear episodes only.
- No LLM-based verification, ever (doctrine, not a phase limitation).

— **MoreSalamander StudioLabs** · *Scientia Ludusque*
