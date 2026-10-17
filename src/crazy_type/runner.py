"""Animation runner: play a TTE effect or fall back to plain text."""

from __future__ import annotations

import difflib
import sys

import pyfiglet

from .catalog import effect_classes, effect_names


class UnknownEffectError(Exception):
    """Raised when --effect names something that does not exist."""

    def __init__(self, name: str, suggestions: list[str]) -> None:
        self.name = name
        self.suggestions = suggestions
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        super().__init__(f"unknown effect: {name!r}.{hint} Run 'crazytype effects' to list all effects.")


def resolve_effect(name: str) -> tuple[type, type]:
    """Return (effect class, config class) for *name* or raise UnknownEffectError."""
    mapping = effect_classes()
    if name in mapping:
        return mapping[name]
    suggestions = difflib.get_close_matches(name, effect_names(), n=3, cutoff=0.5)
    raise UnknownEffectError(name, suggestions)


def apply_figlet(text: str, font: str) -> str:
    """Render *text* as ASCII-art banner text. Raises ValueError on bad font."""
    try:
        return pyfiglet.figlet_format(text, font=font).rstrip("\n")
    except pyfiglet.FontNotFound:
        raise ValueError(
            f"unknown figlet font: {font!r}. Run 'pyfiglet -l' to list fonts."
        ) from None


def play_animation(text: str, effect_name: str) -> int:
    """Play *text* through the TTE engine. Returns process exit code.

    Uses the engine's own ``terminal_output`` context manager, which hides the
    cursor, paces frames, and restores terminal state — including on
    Ctrl+C (KeyboardInterrupt -> exit 130 with cursor restored).
    """
    from .terms import restore_cursor

    effect_class, _config_class = resolve_effect(effect_name)
    effect = effect_class(text)
    try:
        with effect.terminal_output() as terminal:
            for frame in effect:
                terminal.print(frame)
    except KeyboardInterrupt:
        restore_cursor()
        print("\ninterrupted", file=sys.stderr)
        return 130
    restore_cursor()
    return 0


def print_plain(text: str) -> int:
    """Print text with no ANSI codes. Always safe for pipes and files."""
    print(text)
    return 0
