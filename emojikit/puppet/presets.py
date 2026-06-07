"""Role-based motion + FX presets — one rig, many emotes.

A Preset parametrizes the renderer's channels (body motion, expression, FX). Applying a
preset to ANY rig produces a different emote, because motion is expressed abstractly
(squeeze/sway/bob/jump, tail bend, blink, hearts/notes/…) rather than per-character.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Preset:
    name: str
    desc: str = ""
    cycles: int = 1            # oscillations of sway/bob per loop
    # body
    squeeze: float = 0.0       # anchored squash amplitude (narrower+taller)
    sway_deg: float = 0.0      # side-to-side rotation about feet
    bob: float = 0.0           # vertical bob (px, + = dip down then up)
    jump: float = 0.0          # bounce up (px)
    droop: float = 0.0         # slump (sy < 1), for sad
    # parts
    tail_amp: float = 15.0     # tail bend amplitude (deg)
    part_cycles: int = 1
    # expression
    blink: bool = False
    heart_eyes: float = 0.0
    blush: float = 0.0
    # color
    tint: tuple | None = None  # ((r,g,b), intensity0..1)
    # streaming FX (intensity 0..1, 0 = off)
    fx_hearts: float = 0.0
    fx_sparkles: float = 0.0
    fx_stars: float = 0.0
    fx_notes: float = 0.0
    fx_confetti: float = 0.0
    # event FX (booleans)
    fx_zzz: bool = False
    fx_exclaim: bool = False
    fx_question: bool = False
    fx_tears: bool = False
    fx_anger: bool = False
    fx_sweat: bool = False


LIBRARY: dict[str, Preset] = {
    "love": Preset("love", "squeeze hug + heart-eyes + floating hearts",
                   squeeze=0.05, sway_deg=1.8, tail_amp=15, blink=True,
                   heart_eyes=1.0, blush=1.0, fx_hearts=1.0, fx_sparkles=0.8),
    "dance": Preset("dance", "groovy sway + bob + music notes",
                    cycles=2, sway_deg=6, bob=10, tail_amp=22, blush=0.4,
                    fx_notes=1.0, fx_sparkles=0.5),
    "celebrate": Preset("celebrate", "jump + confetti + stars",
                        cycles=2, jump=26, tail_amp=20, blush=0.5,
                        fx_confetti=1.0, fx_stars=0.8),
    "happy": Preset("happy", "bouncy + sparkles + stars",
                    cycles=2, jump=16, tail_amp=18, blush=0.6, blink=True,
                    fx_sparkles=1.0, fx_stars=0.5),
    "shocked": Preset("shocked", "jolt + shake + '!'",
                      cycles=3, sway_deg=4, jump=8, tail_amp=26, fx_exclaim=True),
    "confused": Preset("confused", "slow tilt + '?' + sweat",
                       cycles=1, sway_deg=3, tail_amp=8, fx_question=True, fx_sweat=True),
    "sleep": Preset("sleep", "slow breathing + zzz",
                    cycles=1, squeeze=0.03, tail_amp=5, blush=0.2, fx_zzz=True),
    "sad": Preset("sad", "slump + tears + blue tint",
                  cycles=1, droop=0.06, bob=6, tail_amp=4,
                  tint=((90, 130, 200), 0.18), fx_tears=True),
    "angry": Preset("angry", "shake + anger mark + red tint",
                    cycles=3, sway_deg=5, tail_amp=8,
                    tint=((220, 60, 50), 0.16), fx_anger=True),
    "yes": Preset("yes", "nodding (dip down-up x2)",
                  cycles=2, bob=18, tail_amp=10, blush=0.3),
    "no": Preset("no", "head-shake (sway x3)",
                 cycles=3, sway_deg=6, tail_amp=10),
    "shy": Preset("shy", "strong blush + look down + sweat",
                  cycles=1, sway_deg=1.5, bob=6, tail_amp=8, blush=1.0, fx_sweat=True),
}


def get(name: str) -> Preset:
    if name not in LIBRARY:
        raise ValueError(f"unknown preset '{name}'. available: {', '.join(LIBRARY)}")
    return LIBRARY[name]
