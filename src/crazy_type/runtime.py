"""Crazy Type runtime: one canonical playback pipeline for recipes.

Every block draws relative to the cursor row where playback starts, so the
same recipe plays in a standalone terminal and (later) in a Studio preview
region. The pipeline owns cursor visibility, pacing, cancellation and cleanup.
"""

from __future__ import annotations

import os
import random
import shutil
import sys
import time
from typing import Any

from .recipe import RECIPE_FORMAT_VERSION, RecipeError, build_effect_config

HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
RESET = "\x1b[0m"

# True-colour shimmer palette: dim base, bright travelling band, glitch red.
BASE_COLOR = (45, 180, 190)
BAND_COLOR = (220, 255, 250)
GLITCH_COLOR = (255, 90, 90)
GLYPH_POOL = "█▓▒░<>*#?@$%&§"


def _colored(text: str, rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"\x1b[38;2;{r};{g};{b}m{text}{RESET}"


def terminal_size() -> tuple[int, int]:
    """(columns, rows) with safe fallbacks."""
    try:
        size = shutil.get_terminal_size(fallback=(80, 24))
        return max(20, size.columns), max(10, size.lines)
    except Exception:  # noqa: BLE001 - never crash on terminal probing
        return 80, 24


class Pipeline:
    """Owns the screen region and terminal state for one recipe playback."""

    def __init__(self, fps_cap: int = 60) -> None:
        self.width, self.height = terminal_size()
        self.fps_cap = fps_cap
        self._last_frame = 0.0

    def __enter__(self) -> Pipeline:
        sys.stdout.write(HIDE_CURSOR)
        sys.stdout.flush()
        return self

    def __exit__(self, *exc: Any) -> None:
        restore()

    def pace(self) -> None:
        """Cap the frame rate so ambient blocks sip CPU instead of gulping it."""
        if self.fps_cap <= 0:
            return
        wait = 1.0 / self.fps_cap - (time.monotonic() - self._last_frame)
        if wait > 0:
            time.sleep(wait)
        self._last_frame = time.monotonic()

    def run_tte(self, text: str, effect: str, params: dict[str, Any], mode: str) -> None:
        """Play one TTE effect block. Stacked draws below; inplace reuses the region."""
        from .catalog import effect_classes

        effect_cls, _ = effect_classes()[effect]
        config = build_effect_config(effect, params)
        if mode == "inplace":
            import argparse

            from terminaltexteffects.engine.terminal import TerminalConfig

            parser = argparse.ArgumentParser()
            TerminalConfig._populate_parser(parser)
            terminal_config = TerminalConfig._build_config(
                parser.parse_args(["--reuse-canvas"])
            )
            instance = effect_cls(text, config, terminal_config)
            with instance.terminal_output(end_symbol="") as terminal:
                for frame in instance:
                    terminal.print(frame)
        else:
            instance = effect_cls(text, config)
            with instance.terminal_output() as terminal:
                for frame in instance:
                    terminal.print(frame)

    def run_hold(self, seconds: float) -> None:
        time.sleep(seconds)

    def run_grow(
        self,
        text: str,
        fonts: list[str],
        hold_seconds: float,
        end: str,
    ) -> None:
        """Giant growth: word expands through FIGlet sizes, holds, shrinks back."""
        import pyfiglet

        stages: list[list[str]] = []
        for font in fonts:
            try:
                art = pyfiglet.figlet_format(text, font=font).rstrip("\n").split("\n")
            except pyfiglet.FontNotFound as exc:
                raise RecipeError(f"grow block: unknown figlet font {font!r}.") from exc
            width = max(len(line) for line in art)
            if width <= self.width - 1 and len(art) <= self.height - 2:
                stages.append([line.ljust(width) for line in art])
        if not stages:
            print(
                f"[crazytype] grow: no FIGlet stage fits {self.width}x{self.height}; plain text instead.",
                file=sys.stderr,
            )
            print(text)
            return
        clear_width = max(len(line) for stage in stages for line in stage)

        def show(stage: list[str]) -> None:
            for line in stage:
                sys.stdout.write(line.ljust(clear_width) + "\n")
            sys.stdout.flush()

        def hide(nlines: int) -> None:
            sys.stdout.write(f"\x1b[{nlines}A")
            sys.stdout.flush()

        show(stages[0])
        current = stages[0]
        for stage in stages[1:]:
            time.sleep(0.35)
            hide(len(current))
            show(stage)
            current = stage
        time.sleep(hold_seconds)
        for stage in reversed(stages[:-1]):
            time.sleep(0.35)
            hide(len(current))
            show(stage)
            current = stage
        if end == "clear":
            hide(len(stages[0]))
            for _ in range(len(stages[0])):
                sys.stdout.write(" " * clear_width + "\n")
            hide(len(stages[0]))
        else:
            hide(len(stages[0]))
            sys.stdout.write(text + "\n")
        sys.stdout.flush()

    def run_ambient(self, text: str, duration: float, fps: int, seed: int | None) -> None:
        """Living neon: readable text, travelling shimmer, rare seeded glitches."""
        lines = text.split("\n") or [text]
        if os.environ.get("NO_COLOR"):
            # Graceful degradation: hold the readable text, no colour play.
            print(text, flush=True)
            time.sleep(duration)
            return
        rng = random.Random(seed)
        width = max(len(line) for line in lines)
        band = max(2, width // 5)
        glitch_at = rng.randint(30, 70)
        glitch: tuple[str, int, int, int] | None = None  # glyph, line, col, until_frame
        frames = 0
        deadline = time.monotonic() + duration
        period = 1.0 / fps
        # First paint.
        for line in lines:
            sys.stdout.write(_paint_line(line, -band, band, None) + "\n")
        sys.stdout.flush()
        while time.monotonic() < deadline:
            time.sleep(period)
            frames += 1
            pos = (frames * max(1, width // 12)) % (width + 2 * band) - band
            if frames == glitch_at and width > 0:
                line_no = rng.randrange(len(lines))
                col = rng.randrange(max(1, len(lines[line_no])))
                glitch = (rng.choice(GLYPH_POOL), line_no, col, frames + 2)
            sys.stdout.write(f"\x1b[{len(lines)}A")
            for i, line in enumerate(lines):
                g = glitch if glitch is not None and frames <= glitch[3] and i == glitch[1] else None
                sys.stdout.write(_paint_line(line, pos, band, g) + "\n")
            sys.stdout.flush()
            if frames == glitch_at + 8:
                glitch_at = frames + rng.randint(40, 90)
        # Settle on clean, readable text.
        sys.stdout.write(f"\x1b[{len(lines)}A")
        for line in lines:
            sys.stdout.write(_colored(line, BASE_COLOR) + "\n")
        sys.stdout.flush()


def _paint_line(
    line: str, band_pos: int, band_width: int, glitch: tuple[str, int, int, int] | None
) -> str:
    """Paint one ambient frame line: base colour, bright band, optional glitch."""
    parts = []
    for col, char in enumerate(line):
        if char == " ":
            parts.append(" ")
            continue
        if glitch is not None and col == glitch[2]:
            parts.append(_colored(glitch[0], GLITCH_COLOR))
        elif band_pos <= col < band_pos + band_width:
            parts.append(_colored(char, BAND_COLOR))
        else:
            parts.append(_colored(char, BASE_COLOR))
    return "".join(parts)


def restore() -> None:
    """Best-effort cursor restore for every pipeline exit path."""
    try:
        sys.stdout.write(SHOW_CURSOR)
        sys.stdout.flush()
    except Exception:  # noqa: BLE001, S110 - best effort only
        pass


def play_recipe(recipe: dict[str, Any], text: str, force_animate: bool = False) -> int:
    """Play a validated recipe. Returns a process exit code."""
    from .terms import should_animate

    if recipe.get("format_version") != RECIPE_FORMAT_VERSION:
        print("error: unsupported recipe format.", file=sys.stderr)
        return 2
    if force_animate:
        animate, reason = True, "export recording"
    else:
        animate, reason = should_animate()
    if not animate:
        print(f"[crazytype] plain text ({reason})", file=sys.stderr)
        print(text)
        return 0
    seed = recipe.get("seed")
    if seed is not None:
        random.seed(seed)
    try:
        with Pipeline() as pipe:
            for block in recipe["blocks"]:
                kind = block["kind"]
                if kind == "tte":
                    pipe.run_tte(text, block["effect"], block["params"], block["mode"])
                elif kind == "hold":
                    pipe.run_hold(block["seconds"])
                elif kind == "ambient":
                    pipe.run_ambient(
                        text, block["duration_seconds"], block["fps"], block.get("seed", seed)
                    )
                elif kind == "grow":
                    pipe.run_grow(text, block["fonts"], block["hold_seconds"], block["end"])
                else:  # validated earlier; defence in depth
                    raise RecipeError(f"unknown block kind {kind!r}.")
    except KeyboardInterrupt:
        restore()
        print("\ninterrupted", file=sys.stderr)
        return 130
    restore()
    return 0
