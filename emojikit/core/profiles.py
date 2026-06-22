"""Platform output specifications — the single source of truth for sizes and byte budgets.

Sources (verified 2026-06):
  - Slack:   128px emoji, < 128 KB.
  - Discord: 128px custom emoji, < 256 KB.
  - Twitch:  28 / 56 / 112 px (all three required), GIF < 1 MB
             (manual-upload mode: < 512 KB each), <= 60 frames.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Platform:
    name: str
    sizes: tuple[int, ...]          # px squares to export
    static_budget: int              # max bytes for a PNG at each size
    animated_budget: int            # max bytes for a GIF at each size
    max_frames: int = 60

    def primary_size(self) -> int:
        return max(self.sizes)


KB = 1024
MB = 1024 * 1024

SLACK = Platform("slack", sizes=(128,), static_budget=128 * KB, animated_budget=128 * KB)
DISCORD = Platform("discord", sizes=(128,), static_budget=256 * KB, animated_budget=256 * KB)
# Twitch manual-mode per-file limit (the strict one) = 512 KB each.
TWITCH = Platform("twitch", sizes=(112, 56, 28), static_budget=512 * KB, animated_budget=512 * KB)

ALL: dict[str, Platform] = {p.name: p for p in (SLACK, DISCORD, TWITCH)}

# The high-quality archive copy we always keep regardless of platform.
MASTER_SIZE = 512

# Animation defaults. Research across emote makers (Twitch/BTTV/7TV guides) is consistent:
# 10-15 fps is the sweet spot for chat emotes - higher fps just inflates the GIF with no
# visible gain at 28px, and a smaller file leaves more palette headroom (cleaner color)
# on busy art. 18 frames @ 15 fps = a 1.2s loop, same duration as the old 24f@20fps.
DEFAULT_FPS = 15
DEFAULT_FRAMES = 18


def resolve(platform: str) -> list[Platform]:
    """Map a CLI '--platform' value to a list of Platform specs."""
    key = platform.lower()
    if key == "all":
        return list(ALL.values())
    if key in ALL:
        return [ALL[key]]
    raise ValueError(f"unknown platform '{platform}'. choose from: {', '.join(ALL)} | all")


def all_sizes(platforms: list[Platform]) -> list[int]:
    """Union of every size required across the given platforms (descending)."""
    sizes = {s for p in platforms for s in p.sizes}
    return sorted(sizes, reverse=True)
