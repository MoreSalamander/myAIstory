# my-AI-story — Constitution

> *The human writes the constraints. The model writes the prose. Python
> decides whether the prose is allowed to exist.*

This is the human-owned doctrine for **my-AI-story**, a MoreSalamander
**StudioLabs** production: a long, multi-episode story generator with
multi-voice text-to-speech narration. It is built under the studio's
**Deterministic Scaffold** thesis — human-owned constraints, AI-powered
synthesis, deterministic verification at every boundary.

This document is written **before** any synthesis code exists. It is the
contract the system is judged against. Code may not relax a rule in this
document; if a rule is wrong, the rule is changed here first, deliberately,
and then the code follows.

---

## The premise my-AI-story must not violate

A multi-episode story is only worth listening to if **episode 7 still
remembers episode 1.** The single hardest problem in long-form generation
is not prose quality — it is *continuity*. A model left to free-run will
rename characters, resurrect the dead, forget established facts, and drift
the theme. That drift is my-AI-story's equivalent of MyMaestro's hallucination:
the failure mode that makes the artifact worse than not existing.

Therefore the central invariant of my-AI-story is:

> **No episode is persisted, and no audio is synthesized, until a
> deterministic verifier confirms the episode is consistent with the
> series bible.**

The series bible is the source of truth. The model proposes episodes; the
bible — enforced by Python — disposes.

---

## The three moves (non-negotiable)

Every my-AI-story run executes these three moves in order, explicitly.

### 1. Explain — human-owned constraints, written first

The human owns, and writes down before generation:

- **The series seed**: character names, theme (dragons / werewolves /
  vampires / etc.), loose plot direction, episode count, tone.
- **The schemas**: what a series bible is, what an episode is, what a
  voice map is. (See `SPEC.md`.)
- **The acceptance criteria**: the deterministic rules an episode must
  satisfy to be persisted and spoken. (See `SPEC.md`.)
- **The voice policy**: which character maps to which TTS voice, and the
  rule that *every spoken line must be attributable to a known speaker.*

These are constraints, not suggestions. The model is never asked to invent
them and never allowed to override them.

### 2. Synthesize — AI does the high-volume work

A local LLM (via Ollama) does the drafting:

- Proposes/updates the series bible from the seed.
- Drafts each episode's prose and dialogue, conditioned on the bible and
  the user's loose plot direction.
- Tags dialogue lines with a speaker.

The model is **one component, not the system.** Its output is a proposal
with no authority. It is never trusted on first emission.

### 3. Verify — deterministic, pure-Python, load-bearing

Before anything is committed or spoken, pure-Python verifiers run:

- **Continuity verifier** — character names, theme, and established facts
  match the bible. Drift is rejected.
- **Structure verifier** — the episode satisfies the schema (required
  beats present, length within bounds, dialogue well-formed).
- **Speaker verifier** — every spoken line maps to a known character or
  the narrator. An unattributable line blocks TTS.

In **phase 2** (sound design — SFX, ambience, mood music) a fourth
verifier joins them:

- **Cue verifier** — every audio cue the model emits must resolve to a
  real asset in the human-curated sound library. The model may only
  *reference* sounds that already exist; it cannot conjure them.

The verifiers are **not LLMs.** This is inherited doctrine from
my-AI-stro: the grader cannot be the thing it is grading, or it compounds
the failure it is meant to catch. Verification is formula-based and
auditable.

**One deliberate exception to the blocking rule.** The continuity,
structure, and speaker gates are *blocking* — fail them and the episode is
not persisted. The phase-2 cue gate is *non-blocking*: an unresolved sound
cue is silently dropped, not treated as episode failure. Rationale: a
missing footstep effect must never prevent a continuity-valid story from
being told. Sound is enhancement; continuity is the premise. This
exception is intentional and scoped to cues only.

---

## Verification is a system property, not a UI warning

This is the lesson MyMaestro paid for with its existence. my-AI-story encodes it
structurally:

- There is a **grounding gate at every persistence boundary.** An episode
  that fails verification is **never written to the series** and **never
  sent to TTS.** It is rejected or routed back for a bounded retry.
- A soft "⚠️ this episode may be inconsistent" banner is **forbidden** as
  the primary defense. The defense is the gate, in code, before persist.
- Retries are **bounded and deterministic.** On verification failure, the
  pipeline may re-prompt with the specific violation, a fixed number of
  times. After the bound, the episode is **skipped and logged**, not
  force-committed.

If you ever find yourself tempted to "just let it through and warn the
user," stop. That is the exact move this studio was founded by rejecting.

---

## Pipeline-shape discipline

my-AI-story inherits the named-stage pipeline shape from the Build It Publisher →
my-AI-stro lineage. Every stage:

- has a **single responsibility**,
- has an **explicit name**,
- takes explicit input and produces explicit output,
- emits **NDJSON events** from a shared vocabulary so the run is
  observable end-to-end from the web UI.

The shared event vocabulary (`step_start` / `step_complete` / `token` /
`done` / `error`, plus my-AI-story-specific events) is defined in
`ARCHITECTURE.md`. No stage may do work invisibly.

---

## Trust isolation

Following my-AI-stro's model-routing discipline: the role that **owns the
bible** (canonical continuity facts) and the role that **drafts episodes**
are conceptually separate trust domains, even if they share a base model
today. Bible writes go through verification; episode drafts have no write
authority over the bible except via a verified bible-update stage. A
model's prose output never silently edits canon.

---

## Role boundaries (human vs. AI)

| Concern | Owner |
|---|---|
| Series seed, theme, character names, plot direction | **Human** |
| Schemas and acceptance criteria | **Human** |
| Voice assignment policy | **Human** |
| Bible drafting / episode prose / dialogue | **AI (local LLM)** |
| Whether an episode is consistent enough to persist | **Python verifier** |
| Whether a line may be spoken | **Python verifier** |
| What ships | **Human** |

Neither party does the other's job. Both are visible in the result.

---

## Local-first

my-AI-story runs locally, matching the my-AI-stro precedent:

- **Synthesis**: local LLM via Ollama. No story content leaves the
  machine for a cloud model.
- **TTS**: local / open-source engine (Coqui-XTTS, Piper, or equivalent),
  pluggable behind a single interface.
- **Storage**: local filesystem. A series is a directory of verified
  episode artifacts plus the bible.

No per-call cost, no API key required to generate. This is a constraint,
not an accident: the studio's flagship is local-first, and my-AI-story is a
sibling, not a cloud rewrite.

---

## On AI collaboration

my-AI-story is co-authored with AI, disclosed openly per studio brand identity.
The human designs the constraints, defines acceptance criteria, judges
output, and decides what ships. The AI performs high-volume synthesis
inside the constraints. The collaboration is the method, not a secret.

---

## Amending this Constitution

This document is the doctrine. To change a rule: edit it **here**, in a
deliberate commit that states why, **before** changing any code that
depends on it. Code drift from this document is a bug in the code, not in
the document.

— **MoreSalamander StudioLabs**
*Scientia Ludusque*
