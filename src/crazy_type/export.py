"""Export: validated recipe files and asciicast recordings.

Two honest formats (see ADR-6):
- Editable Recipe: the validated .json itself (``crazytype export recipe --recipe out.json``).
- ANSI Recording: asciicast v2 of one real playback, stamped with the terminal
  size it was recorded at (``--cast out.cast``). Replay with any asciicast
  player; ``cat`` replays frames without timing.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any


class CastWriter:
    """File-like stdout proxy recording (timestamp, data) output events."""

    def __init__(self, handle: Any, width: int, height: int) -> None:
        self.handle = handle
        self.start = time.monotonic()
        header = {"version": 2, "width": width, "height": height, "env": {"TERM": "xterm-256color"}}
        handle.write(json.dumps(header) + "\n")

    def _event(self, data: str) -> None:
        self.handle.write(json.dumps([round(time.monotonic() - self.start, 3), "o", data]) + "\n")

    def write(self, data: str) -> int:
        if data:
            self._event(data)
        return len(data)

    def flush(self) -> None:
        self.handle.flush()

    def isatty(self) -> bool:
        return True  # the recording stands in for a terminal


def export_recipe(
    recipe: dict[str, Any],
    text: str,
    recipe_path: str | None = None,
    cast_path: str | None = None,
    force_plain: bool = False,
) -> int:
    """Validate, then write the requested export artifacts. Returns exit code."""
    from .recipe import validate_recipe
    from .runtime import play_recipe, terminal_size

    try:
        recipe = validate_recipe(recipe)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if recipe_path:
        try:
            with open(recipe_path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(recipe, indent=2) + "\n")
        except OSError as exc:
            print(f"error: cannot write {recipe_path}: {exc}", file=sys.stderr)
            return 1
        print(f"[crazytype] recipe exported to {recipe_path}", file=sys.stderr)
    if cast_path:
        width, height = terminal_size()
        try:
            handle = open(cast_path, "w", encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot write {cast_path}: {exc}", file=sys.stderr)
            return 1
        writer = CastWriter(handle, width, height)
        old = sys.stdout
        sys.stdout = writer  # type: ignore[assignment]
        try:
            code = play_recipe(recipe, text, force_animate=True, force_plain=force_plain)
        finally:
            sys.stdout = old
            handle.close()
        print(
            f"[crazytype] recording exported to {cast_path} ({width}x{height}, asciicast v2)",
            file=sys.stderr,
        )
        return code
    if not recipe_path:
        print(json.dumps(recipe, indent=2))
    return 0
