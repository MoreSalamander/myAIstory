"""Sound design (phase 2): the curated cue catalog + non-blocking resolution.

`sound/` is to cues what `tts/` is to voices and `verify/` is to drafts: a
pure-lookup layer with no LLM and no network. The SoundLibrary is human-owned;
the model may only reference tags that already exist in it. Unresolved cues are
dropped (cue_verify is the lone non-blocking gate), then the surviving cues are
handed to mix/ for timeline placement.
"""

from myAIstory.sound.cue import CueDrop, CuePlacement, CuePlan, resolve_cues
from myAIstory.sound.library import Asset, SoundLibrary

__all__ = [
    "SoundLibrary",
    "Asset",
    "resolve_cues",
    "CuePlan",
    "CuePlacement",
    "CueDrop",
]
