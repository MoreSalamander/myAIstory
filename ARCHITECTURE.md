# my-AI-story — Architecture

> The pipeline shape, the named stages, and the event vocabulary. This
> document defines *how the system is structured*; `SPEC.md` defines *what
> each stage must produce and verify*; `CONSTITUTION.md` defines *why*.

my-AI-story is a named-stage pipeline in the Build It Publisher → my-AI-stro
lineage. Each stage has one responsibility, explicit input/output, and
emits NDJSON events so a run is observable end-to-end from the web UI.

---

## System overview

```
                          ┌──────────────────────────────────────┐
   USER (web UI)          │         my-AI-story BACKEND            │
   seed: names, theme,    │   FastAPI  ·  NDJSON event stream      │
   plot direction,  ─────▶│   Ollama (synthesis)  ·  Python (verify)│
   episode count          │   local TTS (pluggable)                │
                          └──────────────────────────────────────┘
                                          │
                                          ▼
                         backend/data/series/<series_id>/
                           bible.json          (source of truth)
                           episodes/NN.json    (verified episode)
                           audio/NN.wav         (stitched narration)
                           events.ndjson        (full run log)
```

- **Stack**: Python backend (FastAPI), Ollama for LLM synthesis, a
  pluggable local TTS engine, a web UI consuming an NDJSON event stream.
- **Storage**: one directory per series. The bible is the source of truth;
  episodes and audio are verified, derived artifacts.

---

## The pipeline stages

Two pipelines share the same event vocabulary.

### Pipeline A — Series initialization (`init`)

Runs once per series, from the user's seed.

```
seed_validate → bible_draft (frame) → arc_plan (one beat per episode)
   → bible_verify → series_persist → done
```

| Stage | Responsibility | In → Out |
|---|---|---|
| `seed_validate` | Pure-Python check that the seed is well-formed (names non-empty, theme in allowed set or free-text, episode count in bounds) | seed → validated seed |
| `bible_draft` | LLM proposes the series bible **frame** — canon characters, theme rules, world facts — but *not* the arc | seed → draft frame |
| `arc_plan` | **Map step:** one LLM call per episode produces that episode's arc beat, grounded in the frame + the beats already planned. The planner auto-samples one fitting **plot shape** from the curated plot kit (§ PlotKit) for the model to specialize to the cast/theme; each beat is gated by `arc_verify` before it joins the arc | frame (+ plot kit) → arc beats ×N |
| `bible_verify` | Pure-Python: the *assembled* bible (frame + full arc) matches the seed — all named characters present, theme honored, arc one-beat-per-episode, schema valid | draft bible → verdict |
| `series_persist` | Write `bible.json` only if verified | bible → series dir |

**Why the arc is a map step.** A small local model reliably writes one good beat
per call but collapses when told to emit all N at once (it stops after a handful
and ignores corrective feedback). So the arc is planned the same way episodes
are — one at a time, each grounded in what came before, each individually
verified (`arc_verify`: valid shape, correct episode number, non-empty summary).
A beat that exhausts its retry budget skips the whole series (a gap in the arc is
an incomplete bible). The unchanged `bible_verify` still guards the boundary: the
fully assembled bible must pass before anything persists. This mirrors the
my-AI-stro advisor, which builds a multi-section study guide one section per call.

### Pipeline B — Episode generation (`episode`)

Runs once per episode, in order. Episode N may read prior episode summaries.

```
context_load → episode_draft → speaker_salvage → continuity_verify
   → structure_verify → speaker_verify → [cue_verify]ᵖ² → voice_assign
   → tts_synth → stitch/mix → episode_persist → bible_update → done
```

ᵖ² = phase-2 stage. In v1 the flow runs without `cue_verify`, and `stitch`
is plain sequential concatenation.

| Stage | Responsibility | In → Out |
|---|---|---|
| `context_load` | Load bible + prior episode summaries → build the constraint context for this episode | series dir → context |
| `episode_draft` | LLM drafts episode prose + speaker-tagged dialogue under context + plot direction | context → draft episode |
| `speaker_salvage` | **Non-blocking cleanup** (the speaker analog of `cue_verify`). Pure-Python, runs before the gates: a dialogue line whose speaker is neither canon/alias, narrator, nor a **declared** newcomer is demoted to narration (text kept, narrator delivers it); a speaker the draft declares in `new_characters` is accepted via an augmented bible/voice-map view so it may speak this episode. Salvageable drafts are cleaned, not skipped; the persistent canon is never touched here | draft → cleaned draft |
| `continuity_verify` | **Gate.** Pure-Python: names/theme/established facts match bible; no contradictions | draft → verdict |
| `structure_verify` | **Gate.** Pure-Python: schema satisfied (beats present, length in bounds, dialogue well-formed) | draft → verdict |
| `speaker_verify` | **Gate.** Pure-Python: every spoken line maps to a known speaker or narrator | draft → verdict |
| `cue_verify` ᵖ² | **Non-blocking gate.** Pure-Python: every `sfx`/`ambience`/`music` cue resolves in the sound library; unresolved cues are dropped, not failed | draft → cleaned cues |
| `voice_assign` | Map each speaker → a TTS voice per the voice policy | episode → voiced script |
| `tts_synth` | Local TTS renders each speech line in its assigned voice | voiced script → line clips |
| `stitch` (→ `mix` ᵖ²) | v1: concatenate line clips in order. Phase 2: mix speech + cues on a timeline — place one-shot sfx, loop/fade `under` beds, duck beds beneath speech | clips (+cues) → `NN.wav` |
| `episode_persist` | Write `episodes/NN.json` + `audio/NN.wav` (only verified episodes reach here) | episode → series dir |
| `bible_update` | Verified bible-update stage: append new world facts, **promote proposed `new_characters` to CanonCharacters** (validated, deduped against existing names/aliases) so later episodes may name them, and flip `status` for `deaths`. The only path by which prose-proposed canon enters the source of truth | episode → updated bible |

**Gate semantics**: `continuity_verify`, `structure_verify`, and
`speaker_verify` are blocking. A failure routes back to `episode_draft`
with the specific violation, for a **bounded** number of retries (default
2). After the bound, the episode is **skipped and logged** — never
force-persisted. See `CONSTITUTION.md`.

`speaker_salvage` runs *before* the gates and is **non-blocking**: it
deterministically cleans the one salvageable failure mode that otherwise
dominated skips (a small model inventing a one-off incidental speaker — a
guard, a blacksmith — instead of using the narrator). It never substitutes for
a gate; anything it cannot legitimately salvage still fails verification
normally. The bounded retries are thus reserved for *real* defects (too short,
a missing beat, a dead character speaking), not for an attribution the system
can repair on its own.

---

## Why `bible_update` is its own verified stage

The episode draft has **no write authority over canon.** New facts (a
character dies, a secret is revealed) only enter the bible through
`bible_update`, which re-validates them against the schema before
appending. This is the trust-isolation rule from `CONSTITUTION.md`:
prose output never silently edits the source of truth.

---

## Event vocabulary (NDJSON)

Every stage emits newline-delimited JSON events on a shared vocabulary,
inherited from my-AI-stro. The web UI renders the run live from this
stream.

| Event | Emitted when | Payload |
|---|---|---|
| `run_start` | A pipeline run begins | `{pipeline, series_id, ts}` |
| `step_start` | A stage begins | `{stage, ts}` |
| `token` | LLM streaming token (draft stages) | `{stage, text}` |
| `step_complete` | A stage finishes OK | `{stage, summary, ts}` |
| `verify_pass` | A gate passes | `{stage, checks}` |
| `verify_fail` | A gate fails (triggers bounded retry) | `{stage, violations, attempt}` |
| `retry` | A draft is re-attempted after a gate failure | `{stage, attempt, reason}` |
| `skip` | Retry bound exhausted; episode skipped | `{stage, reason}` |
| `tts_line` | One speech line rendered to audio | `{speaker, voice, idx}` |
| `cue_place` ᵖ² | One sfx/ambience/music cue placed on the timeline | `{kind, cue, idx, under}` |
| `cue_drop` ᵖ² | A cue tag didn't resolve in the library; dropped | `{kind, cue, idx}` |
| `done` | Pipeline run finished | `{pipeline, result, ts}` |
| `error` | Unrecoverable error | `{stage, message}` |

`verify_fail`, `retry`, and `skip` are my-AI-story-specific additions; the rest
match the studio's existing pipelines so the vocabulary stays portable.

Every event is also appended to `events.ndjson` in the series dir, so a run
is auditable after the fact — not just live.

---

## Module layout

```
backend/myAIstory/
  schemas/        Pydantic models: SeriesSeed, Bible, Episode, VoiceMap
  pipeline/       One module per stage; an orchestrator that emits events
  verify/         Pure-Python verifiers (continuity, structure, speaker)
                  — NO LLM imports allowed in this package
  synth/          Ollama client wrapper (bible_draft, episode_draft)
  plots/          Curated plot grab bag loader + deterministic selector
                  — NO LLM imports allowed (pure catalog lookup, like verify/)
  tts/            Pluggable TTS interface + local backends (Piper, Kokoro, Clone)
  sound/          (phase 2) SoundLibrary loader + cue resolver
  mix/            (phase 2) timeline mixer: ducking, fades, placement
  events.py       NDJSON event emitter
  store.py        Series directory read/write
  api.py          FastAPI app: start runs, stream events
frontend/         Web UI consuming the NDJSON stream
```

The `sound/` resolver and `mix/` mixer are phase-2 additions that bolt onto
the existing pipeline; v1 ships without them. Like `verify/`, `sound/`'s
resolver imports no LLM — cue resolution is a pure lookup against the
manifest.

**Hard rule**: the `verify/` package imports no LLM client and no network
code. A verifier that calls a model is a contradiction in terms.

---

## Observability

A run is observable three ways, all from the same event stream:

1. **Live** — the web UI renders `step_start`/`token`/`verify_*`/`done`
   as the run happens.
2. **Replayable** — `events.ndjson` is the full ordered log; re-render any
   past run from it.
3. **Auditable** — every gate's pass/fail and every skip is in the log, so
   "why didn't episode 5 generate?" always has a recorded answer.

— **MoreSalamander StudioLabs** · *Scientia Ludusque*
