"""Terminal capability and output handling.

Crazy Type animates only when it is safe and polite to do so. Animation is
skipped (plain text is printed instead) when:

- output is redirected to a file or pipe (not a TTY),
- running under CI (``CI``, ``GITHUB_ACTIONS``, ``TF_BUILD``, ...),
- ``TERM=dumb``,
- ``NO_COLOR`` is set (https://no-color.org/),
- a reduced-motion preference is set (``REDUCED_MOTION`` /
  ``PREFERS_REDUCED_MOTION`` / ``CRAZYTYPE_REDUCED_MOTION``),
- ``--plain`` is passed.
"""

from __future__ import annotations

import os
import shutil
import sys

SHOW_CURSOR = "\x1b[?25h"

_CI_MARKERS = (
    "CI",
    "CONTINUOUS_INTEGRATION",
    "GITHUB_ACTIONS",
    "GITLAB_CI",
    "JENKINS_URL",
    "TF_BUILD",
    "TEAMCITY_VERSION",
)

_REDUCED_MOTION_VARS = (
    "REDUCED_MOTION",
    "PREFERS_REDUCED_MOTION",
    "CRAZYTYPE_REDUCED_MOTION",
)


def _truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


# Glyphs the animation engine needs the console to render. Probed against
# sys.stdout.encoding before animating (found via a real cp1252 ConPTY crash).
GLYPH_PROBE = "\u2588\u2593\u2592\u2591<>*#"


def console_supports_glyphs() -> tuple[bool, str]:
    """True when the console encoding can render animation glyphs."""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        GLYPH_PROBE.encode(encoding)
        return True, encoding
    except (LookupError, UnicodeEncodeError):
        return False, encoding


def running_in_ci() -> bool:
    """True when any well-known CI marker environment variable is set."""
    for marker in _CI_MARKERS:
        value = os.environ.get(marker)
        if value is None:
            continue
        if marker == "CI":
            if _truthy(value):
                return True
        elif str(value).strip():
            return True
    return False


def reduced_motion_requested() -> bool:
    """True when the user prefers reduced motion."""
    return any(_truthy(os.environ.get(var)) for var in _REDUCED_MOTION_VARS)


def should_animate(force_plain: bool = False) -> tuple[bool, str]:
    """Decide whether to animate. Returns (animate, reason)."""
    if force_plain:
        return False, "--plain requested"
    if not sys.stdout.isatty():
        return False, "output is not a terminal (redirected)"
    if running_in_ci():
        return False, "CI environment detected"
    if os.environ.get("TERM") == "dumb":
        return False, "dumb terminal"
    if "NO_COLOR" in os.environ:
        return False, "NO_COLOR is set"
    if reduced_motion_requested():
        return False, "reduced motion requested"
    ok, encoding = console_supports_glyphs()
    if not ok:
        return False, (
            f"console encoding {encoding} cannot render animation glyphs "
            "(use Windows Terminal or 'chcp 65001')"
        )
    return True, "terminal supports animation"


def terminal_width(default: int = 80) -> int:
    """Current terminal width, with a safe fallback."""
    try:
        return shutil.get_terminal_size(fallback=(default, 24)).columns
    except Exception:  # noqa: BLE001 - never crash on terminal probing
        return default


def restore_cursor() -> None:
    """Best-effort cursor restore for our own exit paths.

    The TTE ``terminal_output`` context manager already restores the cursor
    after a normal animation; this covers interrupts and plain exits.
    """
    try:
        if sys.stdout.isatty():
            sys.stdout.write(SHOW_CURSOR)
            sys.stdout.flush()
    except Exception:  # noqa: BLE001, S110 - best effort only
        pass
