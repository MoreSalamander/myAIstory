"""Audition every Kokoro voice on the same line, stitched into one WAV.

Renders, for each voice in the backend's registry, a short clip that first
*announces its own voice id* and then speaks a shared sample line — so the
result is a single self-labeling audio file you can scrub through to pick a
cast. Pure use of the existing TTS seam; nothing in the pipeline changes.

    python -m scripts.audition_voices                       # all voices
    python -m scripts.audition_voices --out /tmp/demo.wav    # custom path
    python -m scripts.audition_voices --line "Your text."    # custom line
    python -m scripts.audition_voices --voices af_heart am_fenrir bm_george
"""

from __future__ import annotations

import argparse
from pathlib import Path

from myAIstory import store
from myAIstory.tts import KokoroTTS, stitch

SAMPLE_LINE = ("The hoard glittered beneath the dying volcano, "
               "and Ember knew the reckoning had come.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audition Kokoro voices.")
    parser.add_argument("--dir", default=str(store.DATA_ROOT / "voices_kokoro"),
                        help="Kokoro model directory (default: data/voices_kokoro)")
    parser.add_argument("--out", default="/tmp/kokoro_voice_audition.wav",
                        help="output WAV path")
    parser.add_argument("--line", default=SAMPLE_LINE, help="the shared line to speak")
    parser.add_argument("--voices", nargs="*", help="only these voice ids (default: all)")
    parser.add_argument("--gap-ms", type=int, default=700,
                        help="silence between voices (ms)")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="delivery speed (1.0 = natural; <1 is slower/sultrier)")
    args = parser.parse_args(argv)

    eng = KokoroTTS(args.dir, speed=args.speed)
    ids = args.voices or [v.id for v in eng.voices()]

    per_voice = []
    for i, vid in enumerate(ids):
        # Spoken label in the voice itself (tight gap), then the shared line.
        label = eng.synth(text=f"Voice {vid.replace('_', ' ')}.", voice=vid)
        line = eng.synth(text=args.line, voice=vid)
        per_voice.append(stitch([label, line], gap_ms=250))
        print(f"[{i + 1}/{len(ids)}] {vid}")

    # Looser gap between voices so each audition is clearly separated.
    track = stitch(per_voice, gap_ms=args.gap_ms)
    Path(args.out).write_bytes(track.to_wav())
    print(f"\n{len(ids)} voices -> {args.out}  ({track.duration:.1f}s @ {track.sample_rate} Hz)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
