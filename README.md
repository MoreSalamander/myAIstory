# my-AI-story

> *Many episodes, one story. Continuity is the thread.*

**my-AI-story** is a long, multi-episode story generator with multi-voice
text-to-speech narration. You give it a seed — character names, a theme
(dragons, werewolves, vampires, …), and a loose plot direction — and it
generates a coherent serialized story, episode after episode, narrated as
audio with a distinct voice for each character.

A **MoreSalamander StudioLabs** production — the storytelling sibling of
[my-AI-stro](https://github.com/kroeone29-sys/myAistro). Where my-AI-stro
verifies *knowledge*, my-AI-story verifies *narrative continuity*: same
thesis, new medium.

---

## What it does

1. You provide a **seed**: title, theme, characters, loose plot direction,
   how many episodes, per-episode length.
2. my-AI-story drafts a **series bible** — the canonical source of truth for
   characters, world facts, and the arc.
3. For each episode, a local LLM drafts prose + speaker-tagged dialogue,
   **verified against the bible** before anything is kept.
4. Verified episodes are rendered to audio with **per-character voices**
   via a local TTS engine, then stitched into one narrated episode.
5. New canon (a death, a reveal, a new character) is fed back into the
   bible through a verified update step — so episode 7 still remembers
   episode 1.

Everything runs **locally**: Ollama for synthesis, a local/open-source TTS
engine for voices, the filesystem for storage. No API keys required to
generate, no story content leaves the machine.

---

## Why it's built this way

my-AI-story is built under the MoreSalamander **Deterministic Scaffold** thesis:

> *A well-fenced LLM inside a deterministic scaffold becomes reliable as a
> system, because the unreliable component is wrapped in reliable ones that
> decide whether to trust each output.*

The three moves, applied to serialized fiction:

1. **Explain (human-owned)** — the schemas, the voice policy, and the
   acceptance criteria are written down first, in `CONSTITUTION.md`,
   `ARCHITECTURE.md`, and `SPEC.md`. The constraints exist before any
   prose is generated.
2. **Synthesize (AI)** — a local LLM does the high-volume drafting of the
   bible, the episodes, and the dialogue.
3. **Verify (deterministic)** — pure-Python verifiers gate every episode
   on continuity, structure, and speaker-attribution **before** it is
   persisted or spoken. The grader is never an LLM.

The hard problem in long-form generation isn't prose quality — it's
**continuity**. A free-running model renames characters, forgets facts,
and drifts the theme. my-AI-story's answer is the same one my-AI-stro gave to
hallucination: **make verification a load-bearing layer in the pipeline,
not a warning at the UI.** No episode is kept or narrated until Python
confirms it's consistent with the bible.

This is the same instinct that runs through the studio's other work — the
named-stage pipeline shape from the Build It Publisher, the
verification-at-every-boundary discipline from MyMaestro's failure — applied
to a new medium.

---

## The documents (read these first)

my-AI-story is constraint-document-first. The doctrine is written before the code
and is the contract the code is judged against:

- **[CONSTITUTION.md](CONSTITUTION.md)** — the human-owned doctrine: the
  three moves, verification-as-system-property, role boundaries.
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — the named-stage pipeline, the
  stages, and the NDJSON event vocabulary.
- **[SPEC.md](SPEC.md)** — the schemas (seed, bible, episode, voice map)
  and the exact acceptance criteria each verifier enforces.

---

## Status

**Founding phase — Explain complete, Synthesize/Verify in progress.** The
constraint documents are written. Implementation of the pipeline against
them is the current work.

---

## On AI collaboration

my-AI-story is co-authored with AI, disclosed openly per studio brand identity.
The human designs the constraints, defines acceptance criteria, judges
output, and decides what ships; the AI performs high-volume synthesis
inside the constraints. Neither party does the other's job.

— **MoreSalamander StudioLabs**
*Scientia Ludusque — Knowledge and Play*
