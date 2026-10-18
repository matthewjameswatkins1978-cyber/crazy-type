"""Crazy Type command line interface.

One coherent CLI for humans and machines::

    crazytype "Hello world"                 # animate with the default effect
    crazytype "ERROR: failure" --auto       # let the Auto Director choose
    crazytype "Hello" --effect decrypt      # pick an explicit effect
    crazytype "Hello" --random              # surprise me (--seed N replays it)
    crazytype "Hello" --calm | --chaos      # mood presets (pools of TTE effects)
    echo "piped text" | crazytype           # pipes work, plain text when redirected
    crazytype effects [--json]              # list the catalogue
    crazytype doctor [--json]               # environment diagnostics
    crazytype --demo                        # interactive showcase
    crazytype --version

Exit codes: 0 success, 1 runtime error / no input, 2 usage error, 130 interrupted.
Diagnostics go to stderr; stdout stays clean and composable with pipes.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

from . import __version__
from .catalog import discover_effects
from .director import DEFAULT_EFFECT, auto_select, pick_preset, pick_random
from .runner import UnknownEffectError, apply_figlet, play_animation, print_plain
from .terms import restore_cursor, running_in_ci, should_animate, terminal_width

# Effects showcased by --demo: (effect, sample line). At least 10, all beautiful.
DEMO_SHOWCASE: tuple[tuple[str, str], ...] = (
    ("decrypt", "Hi, agent."),
    ("beams", "Light show"),
    ("fireworks", "Tests passed!"),
    ("pour", "Welcome!"),
    ("waves", "Stay calm."),
    ("burn", "Warning!"),
    ("errorcorrect", "ERROR: failure"),
    ("rain", "Let it rain"),
    ("unstable", "Reality glitch"),
    ("synthgrid", "Retro future"),
    ("spotlights", "Center stage!"),
    ("print", "Fresh off the press."),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crazytype",
        description="Fast, playful terminal-text animations for humans and AI agents.",
        epilog=(
            "examples:\n"
            '  crazytype "Hello world"\n'
            '  crazytype "ERROR: failure" --auto\n'
            '  crazytype "Hello" --effect decrypt\n'
            '  crazytype "Hello" --random --seed 7\n'
            '  echo "from a pipe" | crazytype --effect waves\n'
            "  crazytype --demo\n"
            "  crazytype effects\n"
            "  crazytype doctor --json\n"
            "  crazytype play giant-growth \"Hello\"\n"
            "  crazytype blocks --json\n"
            "  crazytype studio [recipe]\n"
            "\nSet CRAZYTYPE_PLAIN=1 or pass --plain to disable animation. "
            "NO_COLOR, CI, dumb terminals and reduced-motion preferences are respected."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("text", nargs="?", help="Text to animate. Reads piped stdin when omitted.")
    parser.add_argument("--version", action="version", version=f"crazytype {__version__}")

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--effect", "-e", metavar="NAME", help="Animate with this effect (see 'crazytype effects').")
    mode.add_argument("--auto", action="store_true", help="Let the Auto Director pick an effect for your text.")
    mode.add_argument("--random", action="store_true", help="Pick a random effect (use --seed N to replay it).")
    mode.add_argument("--calm", action="store_true", help="Pick a random gentle effect.")
    mode.add_argument("--chaos", action="store_true", help="Pick a random wild effect.")

    parser.add_argument("--seed", type=int, default=None, help="Seed for --random/--calm/--chaos (deterministic replay).")
    parser.add_argument(
        "--figlet",
        nargs="?",
        const="slant",
        default=None,
        metavar="FONT",
        help="Render text as an ASCII-art banner first (default font: slant).",
    )
    parser.add_argument("--plain", action="store_true", help="Print plain text, no animation.")
    parser.add_argument("--demo", action="store_true", help="Run the interactive effects showcase.")
    return parser


_SUBCOMMANDS = ("effects", "doctor", "play", "blocks", "studio", "export")


def parse_subcommand(argv: list[str]) -> int | None:
    """Handle `crazytype effects|doctor [--json]` before the main parser runs.

    Returns an exit code when argv routes to a subcommand, else None.
    Pre-routing avoids argparse ambiguity between the ``text`` positional
    and subcommand names (and still honours ``--`` for literal text).
    """
    if not argv or argv[0] not in _SUBCOMMANDS or argv[0].startswith("-"):
        return None
    command = argv[0]
    if command == "play":
        sub = argparse.ArgumentParser(prog="crazytype play")
        sub.add_argument("recipe", help="Recipe file (.json) to play.")
        sub.add_argument("text", nargs="?", help="Text to animate. Reads piped stdin when omitted.")
        sub_args = sub.parse_args(argv[1:])
        return cmd_play(sub_args.recipe, sub_args.text)
    if command == "studio":
        sub = argparse.ArgumentParser(prog="crazytype studio")
        sub.add_argument("recipe", nargs="?", help="Recipe name or .json path to open (blank if omitted).")
        sub_args = sub.parse_args(argv[1:])
        return cmd_studio(sub_args.recipe)
    if command == "blocks":
        sub = argparse.ArgumentParser(prog="crazytype blocks")
        sub.add_argument("--json", action="store_true", help="Machine-readable block catalogue.")
        sub_args = sub.parse_args(argv[1:])
        return cmd_blocks(sub_args.json)
    if command == "export":
        sub = argparse.ArgumentParser(prog="crazytype export")
        sub.add_argument("recipe", help="Recipe name or .json path.")
        sub.add_argument("text", nargs="?", help="Text to perform. Reads piped stdin when omitted.")
        sub.add_argument("--recipe", dest="recipe_out", default=None, help="Write validated recipe JSON here.")
        sub.add_argument("--cast", dest="cast_out", default=None, help="Write asciicast v2 recording here.")
        sub_args = sub.parse_args(argv[1:])
        return cmd_export(sub_args.recipe, sub_args.text, sub_args.recipe_out, sub_args.cast_out)
    sub = argparse.ArgumentParser(prog=f"crazytype {command}")
    sub.add_argument("--json", action="store_true", help="Machine-readable JSON output (no ANSI codes).")
    sub_args = sub.parse_args(argv[1:])
    if command == "effects":
        return cmd_effects(sub_args.json)
    return cmd_doctor(sub_args.json)


def read_input(arg_text: str | None) -> str | None:
    """Direct argument wins; otherwise read piped stdin; None when there is no input."""
    if arg_text is not None:
        return arg_text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return None


def cmd_effects(as_json: bool) -> int:
    effects = discover_effects()
    if as_json:
        payload = {
            "effects": [
                {"name": info.name, "title": info.title, "description": info.help} for info in effects
            ]
        }
        print(json.dumps(payload, indent=2))
    else:
        print(f"{len(effects)} effects (engine: terminaltexteffects):\n")
        width = max(len(info.name) for info in effects)
        for info in effects:
            blurb = f" - {info.help}" if info.help else ""
            print(f"  {info.name:<{width}}{blurb}")
        print("\nTry: crazytype \"Hello\" --effect decrypt")
    return 0


def doctor_payload() -> dict:
    try:
        tte_version = pkg_version("terminaltexteffects")
    except PackageNotFoundError:
        tte_version = "unknown"
    try:
        figlet_version = pkg_version("pyfiglet")
    except PackageNotFoundError:
        figlet_version = "unknown"
    animate, reason = should_animate()
    return {
        "crazytype": __version__,
        "python": platform.python_version(),
        "platform": sys.platform,
        "terminaltexteffects": tte_version,
        "pyfiglet": figlet_version,
        "tty": sys.stdout.isatty(),
        "terminal_width": terminal_width(),
        "animate": animate,
        "animate_reason": reason,
        "no_color": "NO_COLOR" in os.environ,
        "ci": running_in_ci(),
        "effects_count": len(discover_effects()),
    }


def cmd_doctor(as_json: bool) -> int:
    payload = doctor_payload()
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
    return 0


def cmd_play(recipe_source: str, arg_text: str | None) -> int:
    from .recipe import RecipeError, load_recipe
    from .runtime import play_recipe

    try:
        recipe = load_recipe(_builtin_or_path(recipe_source))
    except RecipeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    raw = read_input(arg_text)
    if raw is None:
        print("error: no input. Give text or pipe it in. See 'crazytype play --help'.", file=sys.stderr)
        return 2
    text = raw.strip("\n")
    if not text.strip():
        print("error: no input (empty text).", file=sys.stderr)
        return 1
    return play_recipe(recipe, text)


def _builtin_or_path(source: str) -> str:
    """Allow bundled recipe names ('giant-growth') as shorthand for their files."""
    import importlib.resources

    try:
        bundled = importlib.resources.files("crazy_type") / "recipes" / f"{source}.json"
        if bundled.is_file():
            return str(bundled)
    except Exception:  # noqa: BLE001 - fall through to plain path handling
        pass
    return source


def cmd_blocks(as_json: bool) -> int:
    from .recipe import BLOCK_SPECS, block_catalogue

    if as_json:
        print(json.dumps(block_catalogue(), indent=2))
        return 0
    print("Recipe blocks (see 'crazytype blocks --json' for the machine-readable catalogue):\n")
    for kind, spec in BLOCK_SPECS.items():
        print(f"  {kind} - {spec['help']}")
    print("\nBundled recipes: giant-growth, living-neon, particle-reconstruction")
    print("Try: crazytype play giant-growth \"Hello\"")
    return 0


def cmd_export(recipe_arg: str, arg_text: str | None, recipe_out: str | None, cast_out: str | None) -> int:
    from .export import export_recipe
    from .recipe import RecipeError, load_recipe

    try:
        recipe = load_recipe(_builtin_or_path(recipe_arg))
    except RecipeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if cast_out is None and recipe_out is None:
        print("error: give --recipe and/or --cast output paths. See 'crazytype export --help'.", file=sys.stderr)
        return 2
    raw = read_input(arg_text)
    if raw is None:
        print("error: no input. Give text or pipe it in.", file=sys.stderr)
        return 2
    text = raw.strip("\n")
    if not text.strip():
        print("error: no input (empty text).", file=sys.stderr)
        return 1
    return export_recipe(recipe, text, recipe_out, cast_out)


def cmd_studio(recipe_arg: str | None) -> int:
    from .recipe import RecipeError, load_recipe
    from .studio import Studio, blank_recipe, run_studio

    if recipe_arg:
        try:
            recipe = load_recipe(_builtin_or_path(recipe_arg))
        except RecipeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        path = recipe_arg
    else:
        recipe = blank_recipe()
        path = None
    state = Studio(recipe)
    # Only real user files are save destinations; bundled shorthands and
    # package-internal paths must ask instead of writing junk or overwriting
    # shipped data (see saveable_path).
    from .studio import saveable_path

    state.path = saveable_path(path)
    return run_studio(state)


def cmd_demo() -> int:
    if not sys.stdout.isatty():
        print("error: --demo needs an interactive terminal.", file=sys.stderr)
        return 1
    print("Crazy Type demo — Enter for next effect, q + Enter to quit.\n")
    try:
        for name, sample in DEMO_SHOWCASE:
            print(f"--- {name} ---")
            code = play_animation(sample, name)
            if code != 0:
                return code
            try:
                answer = input("[Enter]=next effect  q=quit ")
            except EOFError:
                break
            if answer.strip().lower() in {"q", "quit", "exit"}:
                break
    except KeyboardInterrupt:
        restore_cursor()
        print("\ninterrupted", file=sys.stderr)
        return 130
    restore_cursor()
    print("\nThat's Crazy Type. Run 'crazytype effects' to see them all.")
    return 0


def choose_effect(args: argparse.Namespace, text: str) -> tuple[str, str | None]:
    """Return (effect_name, note_for_stderr)."""
    if args.effect:
        return args.effect, None
    if args.auto:
        name, reason = auto_select(text)
        return name, f"[crazytype] auto: {name} ({reason})"
    if args.random:
        name, seed = pick_random(args.seed)
        return name, f"[crazytype] random: {name} (seed {seed})"
    if args.calm:
        name, seed = pick_preset("calm", args.seed)
        return name, f"[crazytype] calm: {name} (seed {seed})"
    if args.chaos:
        name, seed = pick_preset("chaos", args.seed)
        return name, f"[crazytype] chaos: {name} (seed {seed})"
    return DEFAULT_EFFECT, None


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    subcommand_result = parse_subcommand(raw_argv)
    if subcommand_result is not None:
        return subcommand_result

    parser = build_parser()
    args = parser.parse_args(raw_argv)

    if args.demo:
        return cmd_demo()

    raw = read_input(args.text)
    if raw is None:
        print("error: no input. Give text or pipe it in. See 'crazytype --help'.", file=sys.stderr)
        return 2
    text = raw.strip("\n")
    if not text.strip():
        print("error: no input (empty text).", file=sys.stderr)
        return 1

    if args.figlet is not None:
        try:
            text = apply_figlet(text, args.figlet)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    effect_name, note = choose_effect(args, text)
    if note:
        print(note, file=sys.stderr)

    # Resolve early so a typoed --effect always errors, even on plain fallback.
    from .runner import resolve_effect

    try:
        resolve_effect(effect_name)
    except UnknownEffectError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    force_plain = args.plain or _truthy_env("CRAZYTYPE_PLAIN")
    animate, reason = should_animate(force_plain=force_plain)
    if not animate:
        if args.effect or args.auto or args.random or args.calm or args.chaos:
            print(f"[crazytype] plain text ({reason})", file=sys.stderr)
        return print_plain(text)

    try:
        return play_animation(text, effect_name)
    except UnknownEffectError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
