"""Record an asciicast of a Studio remix session — in-process, no ConPTY.

Drives the REAL editor with injected keystrokes while capturing its REAL
frame stream through CastWriter. Deterministic, fast, platform-independent,
and CI-friendly. Output: docs/demo/studio-remix.cast (asciicast v2).

Replay:  npx asciinema play docs/demo/studio-remix.cast
"""

from __future__ import annotations

import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conpty_dogfood import REPO  # noqa: E402  (for REPO)

sys.path.insert(0, os.path.join(REPO, "src"))
from crazy_type.cli import _builtin_or_path  # noqa: E402
from crazy_type.export import CastWriter  # noqa: E402
from crazy_type.recipe import load_recipe  # noqa: E402
from crazy_type.studio import Studio, run_studio  # noqa: E402

OUT = os.path.join(REPO, "docs", "demo", "studio-remix.cast")
COLS, ROWS = 100, 30
KEY_DELAY = 0.9  # seconds per keystroke so replay feels human


def main() -> int:
    recipe = load_recipe(_builtin_or_path("particle-reconstruction"))
    state = Studio(recipe)
    state.message = "Hi"
    state.path = None

    # Script: watch, move, duplicate (remix), preview, undo, quit. No pause
    # key: the "Enter to return" pause only happens when out is sys.stdout.
    # Undo marks dirty, so quitting takes the armed second q.
    keys = ["j", "d", "p", "u", "q", "q"]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        writer = CastWriter(handle, COLS, ROWS)

        def paced(keys=keys, writer=writer):
            for key in keys:
                time.sleep(KEY_DELAY)  # human-looking pacing between presses
                yield key

        # Preview frames write to sys.stdout directly (runtime contract), so
        # point stdout at the cast writer for the whole session.
        real_stdout = sys.stdout
        sys.stdout = writer  # type: ignore[assignment]
        try:
            code = run_studio(state, keys=paced(), out=writer, size=(COLS, ROWS))
        finally:
            sys.stdout = real_stdout
    size = os.path.getsize(OUT)
    print(f"studio exit={code} wrote {OUT} ({size} bytes)", flush=True)
    if code != 0:
        return 1
    # Self-verification: valid header, the scripted story, and real
    # animation frames (TTE writes truecolor SGR; chrome is ASCII-only).
    lines = open(OUT, encoding="utf-8").read().splitlines()
    header = json.loads(lines[0])
    assert header["version"] == 2 and len(lines) > 10
    content = "".join(json.loads(line)[2] for line in lines[1:])
    for token in ("duplicated", "preview finished", "undone", "UNSAVED"):
        assert token in content, f"missing story beat: {token}"
    assert "\x1b[38;2;" in content, "preview did not animate into the cast"
    assert content.count("\x1b[?1049l") == 2  # preview out + final exit
    print(f"header {header['width']}x{header['height']}, {len(lines) - 1} events, self-check OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
