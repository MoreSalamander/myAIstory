"""Procedural starter catalog generator (SPEC §4b "Sourcing").

SPEC ships "a small curated set of free-licensed clips" behind the
`library.json` manifest. To stay fully offline, deterministic, and
licence-free, v1 *synthesizes* that starter set with numpy instead of bundling
downloaded audio — recognizable placeholders (a thud, footsteps, rain, a
tension bed…) that prove the mix path. The pipeline never cares how an asset
was made, only that its tag resolves, so swapping these for real recordings is
a drop-in: replace the files, keep the manifest.

    python -m myAIstory.sound.assets            # write to data/sound_library/
    python -m myAIstory.sound.assets --force    # overwrite existing assets
"""

from __future__ import annotations

import argparse
import json
import wave
from pathlib import Path

import numpy as np

from myAIstory import store

SR = 22050
_RNG = np.random.default_rng(7)  # fixed seed → byte-identical catalog every run


# --- tiny synthesis toolkit --------------------------------------------------

def _t(dur: float) -> np.ndarray:
    return np.linspace(0, dur, int(SR * dur), endpoint=False)


def _noise(dur: float) -> np.ndarray:
    return _RNG.uniform(-1, 1, int(SR * dur))


def _lowpass(x: np.ndarray, k: int) -> np.ndarray:
    return np.convolve(x, np.ones(k) / k, mode="same")


def _highpass(x: np.ndarray, k: int) -> np.ndarray:
    return x - _lowpass(x, k)


def _fade(x: np.ndarray, ms: float = 15.0) -> np.ndarray:
    n = min(int(SR * ms / 1000), len(x) // 2)
    if n <= 0:
        return x
    env = np.ones(len(x))
    env[:n] = np.linspace(0, 1, n)
    env[-n:] = np.linspace(1, 0, n)
    return x * env


def _norm(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = np.max(np.abs(x)) or 1.0
    return x / m * peak


# --- individual assets (each returns float samples in [-1, 1]) ---------------

def door_close() -> np.ndarray:
    t = _t(0.5)
    thud = np.sin(2 * np.pi * 85 * t) * np.exp(-9 * t)
    click = _lowpass(_noise(0.5), 40) * np.exp(-30 * t)
    return _fade(_norm(thud + 0.5 * click))


def footsteps() -> np.ndarray:
    out = np.zeros(int(SR * 1.6))
    step = _lowpass(_noise(0.12), 25)
    step *= np.exp(-22 * _t(0.12))
    for i in range(4):
        s = int(SR * (0.1 + i * 0.38))
        out[s:s + len(step)] += step
    return _fade(_norm(out))


def thunder() -> np.ndarray:
    t = _t(2.2)
    rumble = _lowpass(_noise(2.2), 80)
    swell = np.sin(np.pi * t / 2.2) ** 2
    return _fade(_norm(rumble * swell), ms=120)


def sword_clash() -> np.ndarray:
    t = _t(0.8)
    ring = sum(np.sin(2 * np.pi * f * t) for f in (2100, 3300, 4700))
    ring = ring * np.exp(-7 * t)
    click = _highpass(_noise(0.8), 8) * np.exp(-60 * t)
    return _fade(_norm(ring + click))


def wing_flap() -> np.ndarray:
    out = np.zeros(int(SR * 1.5))
    for i in range(3):
        whoosh = _lowpass(_noise(0.35), 60) * _fade(np.ones(int(SR * 0.35)), 80)
        s = int(SR * (0.05 + i * 0.45))
        out[s:s + len(whoosh)] += whoosh
    return _fade(_norm(out))


def rain() -> np.ndarray:  # loopable bed
    bed = _highpass(_noise(3.0), 6)
    return _fade(_norm(bed, 0.7), ms=200)


def wind() -> np.ndarray:  # loopable bed
    t = _t(4.0)
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.2 * t)
    bed = _lowpass(_noise(4.0), 120) * lfo
    return _fade(_norm(bed, 0.7), ms=300)


def fire_crackle() -> np.ndarray:  # loopable bed
    bed = _lowpass(_noise(3.0), 200) * 0.3
    pops = np.zeros(int(SR * 3.0))
    for _ in range(40):
        s = int(_RNG.uniform(0, SR * 3.0 - 50))
        pops[s:s + 30] += _RNG.uniform(0.4, 1.0) * np.hanning(30)
    return _fade(_norm(bed + pops, 0.7), ms=150)


def _pad(freqs, dur: float, peak: float) -> np.ndarray:
    t = _t(dur)
    sig = sum(np.sin(2 * np.pi * f * t) for f in freqs)
    return _fade(_norm(sig, peak), ms=250)


def tension() -> np.ndarray:  # loopable bed: low beating drone
    t = _t(4.0)
    drone = np.sin(2 * np.pi * 55 * t) + np.sin(2 * np.pi * 55.6 * t)
    swell = 0.6 + 0.4 * np.sin(2 * np.pi * 0.15 * t)
    return _fade(_norm(drone * swell, 0.7), ms=300)


def calm() -> np.ndarray:  # loopable bed: soft major triad
    return _pad((196.0, 246.94, 293.66), 4.0, 0.55)


def triumph() -> np.ndarray:  # loopable bed: bright major chord
    return _pad((261.63, 329.63, 392.0, 523.25), 3.0, 0.7)


# tag → (kind, builder, gain_db, loop, aliases)
CATALOG = {
    "door_close":   ("sfx", door_close, -3.0, False, ["door", "door_slam"]),
    "footsteps":    ("sfx", footsteps, -6.0, False, ["footsteps_gravel", "walking", "steps"]),
    "thunder":      ("sfx", thunder, -2.0, False, ["thunderclap", "storm"]),
    "sword_clash":  ("sfx", sword_clash, -4.0, False, ["sword", "clash", "blade"]),
    "wing_flap":    ("sfx", wing_flap, -5.0, False, ["wings", "wingbeat", "flapping"]),
    "rain":         ("ambience", rain, -10.0, True, ["rainfall", "raining"]),
    "wind":         ("ambience", wind, -11.0, True, ["wind_gust", "breeze", "rustling"]),
    "fire_crackle": ("ambience", fire_crackle, -10.0, True, ["fire", "campfire", "hearth"]),
    "tension":      ("music", tension, -12.0, True, ["suspense", "dread", "ominous"]),
    "calm":         ("music", calm, -13.0, True, ["peaceful", "gentle"]),
    "triumph":      ("music", triumph, -12.0, True, ["victory", "heroic", "fanfare"]),
}


def _write_wav(path: Path, samples: np.ndarray) -> None:
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)


def generate(root: Path | None = None, *, force: bool = False) -> Path:
    """Write every asset + the library.json manifest. Returns the library dir."""
    root = root or (store.DATA_ROOT / "sound_library")
    entries = []
    for tag, (kind, builder, gain_db, loop, aliases) in CATALOG.items():
        rel = f"{kind}/{tag}.wav"
        dest = root / rel
        if force or not dest.exists():
            _write_wav(dest, builder())
        entries.append({
            "tag": tag, "kind": kind, "aliases": aliases,
            "file": rel, "gain_db": gain_db, "loop": loop,
        })
    (root / "library.json").write_text(
        json.dumps({"assets": entries}, indent=2), encoding="utf-8"
    )
    return root


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate the procedural sound catalog.")
    ap.add_argument("--force", action="store_true", help="overwrite existing assets")
    ap.add_argument("--root", help="output dir (default: data/sound_library)")
    args = ap.parse_args(argv)
    root = generate(Path(args.root) if args.root else None, force=args.force)
    print(f"wrote {len(CATALOG)} assets + manifest to {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
