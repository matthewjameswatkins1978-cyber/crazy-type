"""Auto Director: deterministic rules that pick a fitting effect for your text.

Rules are keyword-based, stable, and fully deterministic — the same input
always selects the same effect. Randomness (``--random``/``--calm``/``--chaos``)
is only ever driven by an explicit seed so ``--seed N`` replays exactly.
"""

from __future__ import annotations

import random
import re

# Presets are pools of *existing* TTE effects — no separate rendering engine.
CALM_EFFECTS = ("expand", "middleout", "pour", "print", "slide", "waves", "wipe")
CHAOS_EFFECTS = (
    "burn",
    "decrypt",
    "fireworks",
    "matrix",
    "rain",
    "synthgrid",
    "thunderstorm",
    "unstable",
)

DEFAULT_EFFECT = "decrypt"

_ERROR_RE = re.compile(r"error|fail|exception|traceback|panic|fatal|bug|crash", re.I)
_WARNING_RE = re.compile(r"warn|caution|deprecat|careful|alert|notice", re.I)
_SUCCESS_RE = re.compile(r"success|pass(?:ed|ing)?\b|\bok\b|done\b|built\b|complet|congrat|shipp", re.I)
_STARTUP_RE = re.compile(r"hello|welcome|start|init|launch|crazy|hey\b|hi\b", re.I)


def auto_select(text: str) -> tuple[str, str]:
    """Pick an effect for *text*. Returns (effect_name, reason).

    Precedence is deliberate: errors beat warnings beat success beat startup,
    everything else gets the friendly default.
    """
    lowered = text.lower()
    if _ERROR_RE.search(lowered):
        return "errorcorrect", "error keywords detected"
    if _WARNING_RE.search(lowered):
        return "burn", "warning keywords detected"
    if _SUCCESS_RE.search(lowered):
        return "fireworks", "success keywords detected"
    if _STARTUP_RE.search(lowered):
        return "pour", "greeting/startup keywords detected"
    return DEFAULT_EFFECT, "ordinary text"


def pick_random(seed: int | None = None, pool: tuple[str, ...] | None = None) -> tuple[str, int]:
    """Pick a random effect from *pool* (default: every effect).

    Returns (effect_name, seed_used). A fresh OS seed is drawn when *seed* is
    None; pass ``--seed N`` for a deterministic replay.
    """
    from .catalog import effect_names

    candidates = list(pool) if pool else effect_names()
    rng = random.Random(seed)
    actual_seed = seed if seed is not None else rng.randint(0, 2**31 - 1)
    if seed is None:
        rng = random.Random(actual_seed)
    return rng.choice(candidates), actual_seed


def pick_preset(preset: str, seed: int | None = None) -> tuple[str, int]:
    """Pick a random effect from the ``calm`` or ``chaos`` preset pool."""
    if preset == "calm":
        return pick_random(seed, CALM_EFFECTS)
    if preset == "chaos":
        return pick_random(seed, CHAOS_EFFECTS)
    raise ValueError(f"unknown preset: {preset!r} (choose 'calm' or 'chaos')")
