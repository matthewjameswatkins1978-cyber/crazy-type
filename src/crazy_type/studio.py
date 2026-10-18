"""Crazy Type Studio: keyboard-first terminal editor for recipes.

Design rules: stdlib only (the player stays light), screens share the same
validated recipe model and the same runtime playback as the CLI, and every
exit path restores the terminal. Non-interactive terminals are refused up
front. Run with ``crazytype studio [recipe]``.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from typing import Any, Callable, Iterable

from .recipe import BLOCK_SPECS, RECIPE_FORMAT_VERSION, RecipeError, validate_recipe

ALT_ENTER = "\x1b[?1049h\x1b[H"
ALT_EXIT = "\x1b[?1049l"
HIDE = "\x1b[?25l"
SHOW = "\x1b[?25h"
CLEAR = "\x1b[2J\x1b[H"
RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"

MIN_COLS = 80
MIN_ROWS = 24


# --------------------------------------------------------------------------
# Key reading (Windows + POSIX, stdlib only)
# --------------------------------------------------------------------------
def read_key() -> str:
    """Read one keypress; return 'up/down/left/right/enter/esc/tab' or a char."""
    if os.name == "nt":
        import msvcrt

        first = msvcrt.getch()
        if first in (b"\x00", b"\xe0"):
            second = msvcrt.getch()
            return {b"H": "up", b"P": "down", b"K": "left", b"M": "right"}.get(second, "")
        if first == b"\r":
            return "enter"
        if first == b"\x1b":
            return "esc"
        if first == b"\t":
            return "tab"
        if first == b"\x7f":
            return "backspace"
        try:
            return first.decode("utf-8")
        except UnicodeDecodeError:
            return ""
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        data = os.read(fd, 4)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    if data == b"\x1b[A":
        return "up"
    if data == b"\x1b[B":
        return "down"
    if data == b"\x1b[C":
        return "right"
    if data == b"\x1b[D":
        return "left"
    if data in (b"\r", b"\n"):
        return "enter"
    if data == b"\x1b":
        return "esc"
    if data == b"\t":
        return "tab"
    if data in (b"\x7f", b"\x08"):
        return "backspace"
    try:
        return data[:1].decode("utf-8")
    except UnicodeDecodeError:
        return ""


# --------------------------------------------------------------------------
# Model: validated recipe state with undo/redo
# --------------------------------------------------------------------------
def blank_recipe(name: str = "untitled") -> dict[str, Any]:
    # A blank canvas must do something visible on first preview: open with a
    # friendly effect, not a silent hold (which looks broken to newcomers).
    return validate_recipe(
        {
            "format_version": RECIPE_FORMAT_VERSION,
            "name": name,
            "blocks": [{"kind": "tte", "effect": "decrypt"}],
        }
    )


def snapshot_label(recipe: dict[str, Any]) -> str:
    kinds = [b["kind"] for b in recipe["blocks"]]
    return f"{recipe['name']} [{', '.join(kinds)}]"


class Studio:
    """Editor state. All mutations go through validated snapshots (undo/redo)."""

    def __init__(self, recipe: dict[str, Any], message: str = "Hello") -> None:
        self.recipe = copy.deepcopy(recipe)
        self.message = message
        self.path: str | None = None
        self.selected = 0
        self.screen = "blocks"  # blocks | edit | add | effect | help
        self.status = "j/k move  enter edit  a add  p play  s save  ? help  q quit"
        self.dirty = False
        self._undo: list[dict[str, Any]] = []
        self._redo: list[dict[str, Any]] = []
        self.add_index = 0
        self.effect_filter = ""
        self.effect_index = 0
        self.param_index = 0
        self.effect_target = "add"  # or "edit": what the effect picker confirms into
        self.quit_armed = False  # q once arms a discard-quit, q again confirms

    # -- history ---------------------------------------------------------
    def _commit(self, next_recipe: dict[str, Any], action: str) -> None:
        self._undo.append(copy.deepcopy(self.recipe))
        self._redo.clear()
        self.recipe = next_recipe
        self.dirty = True
        self.selected = min(self.selected, len(self.recipe["blocks"]) - 1)
        self.status = action

    def undo(self) -> None:
        if not self._undo:
            self.status = "nothing to undo"
            return
        self._redo.append(copy.deepcopy(self.recipe))
        self.recipe = self._undo.pop()
        self.dirty = True
        self.selected = min(self.selected, len(self.recipe["blocks"]) - 1)
        self.status = "undone"

    def redo(self) -> None:
        if not self._redo:
            self.status = "nothing to redo"
            return
        self._undo.append(copy.deepcopy(self.recipe))
        self.recipe = self._redo.pop()
        self.dirty = True
        self.status = "redone"

    # -- structural edits -------------------------------------------------
    def _with_blocks(self, blocks: list[dict[str, Any]]) -> dict[str, Any]:
        candidate = copy.deepcopy(self.recipe)
        candidate["blocks"] = blocks
        return validate_recipe(candidate)

    def add_block(self, block: dict[str, Any]) -> None:
        blocks = copy.deepcopy(self.recipe["blocks"])
        blocks.insert(self.selected + 1, block)
        try:
            self._commit(self._with_blocks(blocks), f"added {block['kind']}")
            self.selected += 1
        except RecipeError as exc:
            self.status = f"error: {exc}"

    def remove_selected(self) -> None:
        blocks = copy.deepcopy(self.recipe["blocks"])
        if len(blocks) <= 1:
            self.status = "a recipe needs at least one block"
            return
        removed = blocks.pop(self.selected)
        self._commit(self._with_blocks(blocks), f"removed {removed['kind']}")

    def move_selected(self, delta: int) -> None:
        blocks = copy.deepcopy(self.recipe["blocks"])
        i = self.selected
        j = min(max(i + delta, 0), len(blocks) - 1)
        if i == j:
            return
        blocks[i], blocks[j] = blocks[j], blocks[i]
        self._commit(self._with_blocks(blocks), f"moved to position {j}")
        self.selected = j

    def duplicate_selected(self) -> None:
        blocks = copy.deepcopy(self.recipe["blocks"])
        blocks.insert(self.selected + 1, copy.deepcopy(blocks[self.selected]))
        self._commit(self._with_blocks(blocks), "duplicated")
        self.selected += 1

    def set_param(self, name: str, raw: str) -> None:
        """Parse one param value from user text; validate the whole block."""
        blocks = copy.deepcopy(self.recipe["blocks"])
        block = blocks[self.selected]
        spec = BLOCK_SPECS[block["kind"]]["params"].get(name)
        if spec is None:
            self.status = f"unknown parameter {name!r}"
            return
        try:
            value = _parse_param(spec, raw)
        except RecipeError as exc:
            self.status = f"error: {exc}"
            return
        block[name] = value
        try:
            self._commit(self._with_blocks(blocks), f"set {name} = {value!r}")
        except RecipeError as exc:
            self.status = f"error: {exc}"

    def set_message(self, message: str) -> None:
        if message.strip():
            self.message = message
            self.status = "message updated"

    def rename(self, name: str) -> None:
        if name.strip():
            candidate = copy.deepcopy(self.recipe)
            candidate["name"] = name.strip()
            try:
                self._commit(validate_recipe(candidate), f"renamed to {name.strip()!r}")
            except RecipeError as exc:
                self.status = f"error: {exc}"

    # -- persistence -------------------------------------------------------
    def to_json(self) -> str:
        return json.dumps(self.recipe, indent=2) + "\n"

    def save(self, path: str) -> None:
        try:
            validate_recipe(self.recipe)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self.to_json())
        except (RecipeError, OSError) as exc:
            self.status = f"error: {exc}"
            return
        self.path = path
        self.dirty = False
        self.status = f"saved to {path}"


def param_hint(spec: dict[str, Any], current: Any) -> str:
    """One-line editing hint: type, range/options, default, current value."""
    t = spec["type"]
    kind = (
        "number" if t == (int, float) else "integer" if t is int
        else "JSON object" if t is dict else "comma list" if t is list else "text"
    )
    bits = [kind]
    if "range" in spec:
        bits.append(f"{spec['range'][0]}-{spec['range'][1]}")
    if spec.get("values") is not None:
        bits.append("/".join(spec["values"]))
    return f"[{', '.join(bits)}, now {current!r}]"


def _parse_param(spec: dict[str, Any], raw: str) -> Any:
    """Parse user-typed text into a typed param value (before validation)."""
    text = raw.strip()
    if spec["type"] is dict:
        try:
            value = json.loads(text or "{}")
        except json.JSONDecodeError as exc:
            raise RecipeError(f"give JSON like {{\"typing-speed\": 5}} ({exc})") from None
        if not isinstance(value, dict):
            raise RecipeError("params must be a JSON object.")
        return value
    if spec["type"] is list:
        return [part.strip() for part in text.split(",") if part.strip()]
    if spec["type"] is int and not isinstance(spec["type"], tuple):
        try:
            return int(text)
        except ValueError:
            raise RecipeError(f"{text!r} is not an integer.") from None
    if spec["type"] == (int, float):
        if text == "" and not spec.get("required"):
            return spec.get("default")
        try:
            return float(text) if "." in text else int(text)
        except ValueError:
            raise RecipeError(f"{text!r} is not a number.") from None
    return text


# --------------------------------------------------------------------------
# Rendering (writes to any stream; stdout in production, StringIO in tests)
# --------------------------------------------------------------------------
def block_summary(block: dict[str, Any]) -> str:
    kind = block["kind"]
    if kind == "tte":
        return f"tte {block.get('effect', '?')} ({block.get('mode', 'stacked')})"
    if kind == "hold":
        return f"hold {block.get('seconds', '?')}s"
    if kind == "ambient":
        return f"ambient {block.get('duration_seconds', '?')}s @ {block.get('fps', '?')}fps"
    if kind == "grow":
        fonts = ",".join(block.get("fonts", []))
        return f"grow [{fonts}] end={block.get('end', 'word')}"
    return kind


def render(state: Studio, out: Any, cols: int, rows: int) -> None:
    """Draw one full frame of the editor."""
    w = max(cols, MIN_COLS)

    def write(text: str) -> None:
        # CRLF: a bare LF only moves down, leaving the column staggered on
        # real consoles. Carriage-return every line we own.
        out.write(text.replace("\n", "\r\n"))
    write(CLEAR)
    title = f" Crazy Type Studio - {state.recipe['name']}"
    if state.dirty:
        title += " *"
    write(BOLD + title[:w] + RESET + "\n")
    write(DIM + f" Message: {state.message}"[:w] + RESET + "\n")
    # NOTE: ASCII rule below so Studio survives non-UTF-8 consoles (e.g. a
    # default-CP ConPTY); the animation engine itself still needs UTF-8.
    write("-" * min(w, 200) + "\n")
    if state.screen == "blocks":
        _render_blocks(state, write, w, rows)
    elif state.screen == "edit":
        _render_edit(state, write, w, rows)
    elif state.screen == "add":
        _render_add(state, write, w)
    elif state.screen == "effect":
        _render_effects(state, write, w, rows)
    elif state.screen == "help":
        _render_help(write, w)
    write("-" * min(w, 200) + "\n")
    write((DIM + state.status[:w] + RESET + "\n"))
    write(" q quit, ? help\n")


def _render_blocks(state: Studio, write: Callable[[str], Any], w: int, rows: int) -> None:
    blocks = state.recipe["blocks"]
    write(" Blocks - j/k move, enter edit, a add, d duplicate, x delete, J/K reorder\n")
    room = max(rows - 10, 4)
    start = max(0, min(state.selected - room // 2, len(blocks) - room))
    for i in range(start, min(start + room, len(blocks))):
        marker = ">" if i == state.selected else " "
        line = f" {marker} {i}  {block_summary(blocks[i])}"
        if i == state.selected:
            write(BOLD + line[:w] + RESET + "\n")
        else:
            write(line[:w] + "\n")
    write(DIM + " p play, m message, n rename, s save, S save-as, o open, u undo, r redo"[:w] + RESET + "\n")


def _render_edit(state: Studio, write: Callable[[str], Any], w: int, rows: int) -> None:
    block = state.recipe["blocks"][state.selected]
    spec = BLOCK_SPECS[block["kind"]]["params"]
    names = list(spec)
    state.param_index = min(state.param_index, len(names) - 1)
    write(f" Editing block {state.selected} ({block['kind']}) - enter change, esc back\n")
    for i, name in enumerate(names):
        marker = ">" if i == state.param_index else " "
        line = f" {marker} {name} = {block.get(name)!r}"
        write((BOLD + line[:w] + RESET if i == state.param_index else line[:w]) + "\n")
    _ = rows


def _render_add(state: Studio, write: Callable[[str], Any], w: int) -> None:
    kinds = list(BLOCK_SPECS)
    state.add_index = min(state.add_index, len(kinds) - 1)
    write(" Add block - enter insert after current, esc back\n")
    for i, kind in enumerate(kinds):
        marker = ">" if i == state.add_index else " "
        line = f" {marker} {kind} - {BLOCK_SPECS[kind]['help']}"
        write((BOLD + line[:w] + RESET if i == state.add_index else line[:w]) + "\n")


def _render_effects(state: Studio, write: Callable[[str], Any], w: int, rows: int) -> None:
    from .catalog import effect_names

    names = [n for n in effect_names() if state.effect_filter.lower() in n.lower()]
    state.effect_index = min(state.effect_index, max(len(names) - 1, 0))
    write(" Pick effect - type to filter, enter select, esc back\n")
    write(f" filter: {state.effect_filter}\n")
    room = max(rows - 10, 4)
    start = max(0, min(state.effect_index - room // 2, len(names) - room))
    for i in range(start, min(start + room, len(names))):
        marker = ">" if i == state.effect_index else " "
        line = f" {marker} {names[i]}"
        write((BOLD + line[:w] + RESET if i == state.effect_index else line[:w]) + "\n")


def _render_help(write: Callable[[str], Any], w: int) -> None:
    for line in [
        " Workflow: pick a block, press enter, tweak a value, press p to watch it play.",
        "",
        " j/k or arrows  move selection        enter        edit / confirm",
        " a              add block              d / x        duplicate / delete",
        " J / K          reorder block          u / r        undo / redo",
        " p              play recipe            m / n        message / rename",
        " s / S          save / save-as         o            open recipe",
        " q              back (quit on blocks)  esc          back",
        " ?              this help",
        "",
        " Quitting with unsaved work: q arms it, q again discards, s saves first."
        "",
        " Playback is the same runtime the CLI uses: what you see is what plays.",
    ]:
        write(line[:w] + "\n")


# --------------------------------------------------------------------------
# Controller
# --------------------------------------------------------------------------
def default_block_for(kind: str, effect: str = "decrypt") -> dict[str, Any]:
    if kind == "tte":
        return validate_recipe(
            {"format_version": 1, "name": "t", "blocks": [{"kind": "tte", "effect": effect}]}
        )["blocks"][0]
    if kind == "hold":
        return {"kind": "hold", "seconds": 1.0}
    if kind == "ambient":
        return {"kind": "ambient", "duration_seconds": 8.0, "fps": 10, "seed": None}
    return {"kind": "grow", "fonts": ["mini", "standard", "big"], "hold_seconds": 0.5, "end": "word"}


def prompt_line(prompt_text: str, out: Any) -> str:
    """Ask for a line of text: leave the alt screen, use cooked input, return."""
    out.write(ALT_EXIT + SHOW)
    out.flush()
    try:
        return input(prompt_text)
    except (EOFError, KeyboardInterrupt):
        return ""
    finally:
        out.write(ALT_ENTER + HIDE)
        out.flush()


def run_studio(
    state: Studio,
    keys: Iterable[str] | None = None,
    out: Any = None,
    size: tuple[int, int] | None = None,
) -> int:
    """Main loop. Waterloo: every exit restores the terminal.

    keys/out/size are injectable so tests can drive the editor headlessly.
    """
    import shutil

    out = sys.stdout if out is None else out
    source = iter(keys) if keys is not None else None

    def next_key() -> str:
        if source is not None:
            try:
                return next(source)
            except StopIteration:
                return "q"
        return read_key()

    def term_size() -> tuple[int, int]:
        if size is not None:
            return size
        try:
            s = shutil.get_terminal_size()
            return s.columns, s.lines
        except Exception:  # noqa: BLE001
            return 80, 24

    cols, rows = term_size()
    if cols < 40 or rows < 12:
        print("error: terminal too small for Studio (need 40x12).", file=sys.stderr)
        return 1
    if source is None and not sys.stdin.isatty():
        print("error: Studio needs an interactive terminal.", file=sys.stderr)
        return 1

    out.write(ALT_ENTER + HIDE)
    out.flush()
    try:
        while True:
            cols, rows = term_size()
            render(state, out, cols, rows)
            out.flush()
            key = next_key()
            result = handle_key(state, key, out)
            if result == "quit":
                return 0
            if result == "play":
                play_in_studio(state, out)
    except KeyboardInterrupt:
        return 130
    finally:
        out.write(SHOW + ALT_EXIT)
        try:
            out.flush()
        except Exception:  # noqa: BLE001, S110 - best effort only
            pass


def handle_key(state: Studio, key: str, out: Any) -> str | None:
    """One keypress. Returns 'quit', 'play', or None.

    Navigation rule: q and esc always back out of sub-screens. Only q on the
    main blocks screen quits (possibly arming a discard confirm). No key is
    ever silently dead: unknown keys report themselves on the status line.
    """
    if key == "?":
        state.screen = "help" if state.screen != "help" else "blocks"
        return None
    if key in ("q", "esc"):
        if state.screen != "blocks":
            state.screen = "blocks"
            state.effect_filter = ""
            state.status = "back to blocks"
            return None
        if key == "q":
            return _quit_key(state)
        state.quit_armed = False
        state.status = "kept editing"
        return None
    if state.screen == "help":
        state.screen = "blocks"
        return None
    if state.screen == "blocks":
        return _blocks_key(state, key, out)
    if state.screen == "edit":
        return _edit_key(state, key, out)
    if state.screen == "add":
        return _add_key(state, key, out)
    if state.screen == "effect":
        return _effect_key(state, key, out)
    state.status = f"key {key!r} does nothing here (q backs out)"
    return None


def _quit_key(state: Studio) -> str | None:
    """q on the blocks screen: quit clean, or arm a discard confirm."""
    if not state.dirty:
        return "quit"
    if state.quit_armed:
        return "quit"
    state.quit_armed = True
    state.status = "UNSAVED! q=quit+discard  s=save  esc=keep editing"
    return None


def _blocks_key(state: Studio, key: str, out: Any) -> str | None:
    n = len(state.recipe["blocks"])
    if key not in ("q", "s") and state.quit_armed:
        state.quit_armed = False
        state.status = "kept editing"
    if key in ("j", "down"):
        state.selected = min(state.selected + 1, n - 1)
    elif key in ("k", "up"):
        state.selected = max(state.selected - 1, 0)
    elif key == "enter":
        state.screen = "edit"
        state.param_index = 0
    elif key == "a":
        state.screen = "add"
        state.add_index = 0
    elif key == "d":
        state.duplicate_selected()
    elif key == "x":
        state.remove_selected()
    elif key == "J":
        state.move_selected(1)
    elif key == "K":
        state.move_selected(-1)
    elif key == "u":
        state.undo()
    elif key == "r":
        state.redo()
    elif key == "p":
        return "play"
    elif key == "m":
        state.set_message(prompt_line("Message: ", out))
    elif key == "n":
        state.rename(prompt_line("Recipe name: ", out))
    elif key == "s":
        state.save(state.path or prompt_line("Save to: ", out) or "")
        state.quit_armed = False
    elif key == "S":
        state.save(prompt_line("Save as: ", out))
        state.quit_armed = False
    elif key == "o":
        open_recipe(state, out)
    return None


def _edit_key(state: Studio, key: str, out: Any) -> str | None:
    block = state.recipe["blocks"][state.selected]
    names = list(BLOCK_SPECS[block["kind"]]["params"])
    if key in ("j", "down"):
        state.param_index = min(state.param_index + 1, len(names) - 1)
    elif key in ("k", "up"):
        state.param_index = max(state.param_index - 1, 0)
    elif key == "enter":
        name = names[state.param_index]
        if block["kind"] == "tte" and name == "effect":
            state.screen = "effect"
            state.effect_target = "edit"
            state.effect_index = 0
            state.effect_filter = ""
        else:
            current = block.get(name)
            hint = param_hint(BLOCK_SPECS[block["kind"]]["params"][name], current)
            state.set_param(name, prompt_line(f"{name} {hint}: ", out))
    return None


def _add_key(state: Studio, key: str, out: Any) -> str | None:
    kinds = list(BLOCK_SPECS)
    if key in ("j", "down"):
        state.add_index = min(state.add_index + 1, len(kinds) - 1)
    elif key in ("k", "up"):
        state.add_index = max(state.add_index - 1, 0)
    elif key == "enter":
        kind = kinds[state.add_index]
        if kind == "tte":
            state.screen = "effect"
            state.effect_target = "add"
            state.effect_index = 0
            state.effect_filter = ""
        else:
            state.add_block(default_block_for(kind))
            state.screen = "blocks"
    return None


def _effect_key(state: Studio, key: str, out: Any) -> str | None:
    from .catalog import effect_names

    names = [n for n in effect_names() if state.effect_filter.lower() in n.lower()]
    if key == "enter" and names:
        state.effect_index = min(state.effect_index, len(names) - 1)
        chosen = names[state.effect_index]
        if state.effect_target == "edit":
            state.set_param("effect", chosen)
        else:
            state.add_block(default_block_for("tte", chosen))
        state.screen = "blocks"
        state.effect_filter = ""
        state.effect_target = "add"
    elif key in ("j", "down"):
        state.effect_index = min(state.effect_index + 1, max(len(names) - 1, 0))
    elif key in ("k", "up"):
        state.effect_index = max(state.effect_index - 1, 0)
    elif key == "backspace":
        state.effect_filter = state.effect_filter[:-1]
        state.effect_index = 0
    elif len(key) == 1 and key.isprintable():
        state.effect_filter += key
        state.effect_index = 0
    return None


def open_recipe(state: Studio, out: Any) -> None:
    from .recipe import load_recipe

    from .cli import _builtin_or_path

    answer = prompt_line("Open recipe (name or path): ", out)
    if not answer.strip():
        return
    try:
        loaded = load_recipe(_builtin_or_path(answer.strip()))
    except RecipeError as exc:
        state.status = f"error: {exc}"
        return
    state.recipe = loaded
    state.path = answer.strip()
    state.selected = 0
    state.dirty = False
    state.status = f"opened {loaded['name']}"


def play_in_studio(state: Studio, out: Any) -> None:
    """Preview with the real runtime: leave the alt screen, play, come back."""
    from .runtime import play_recipe

    out.write(ALT_EXIT + SHOW)
    out.flush()
    try:
        code = play_recipe(state.recipe, state.message)
    finally:
        out.write(ALT_ENTER + HIDE)
        out.flush()
    if code == 130:
        state.status = "preview interrupted"
    elif code != 0:
        state.status = f"preview exited with code {code}"
    else:
        state.status = "preview finished - that is exactly what the CLI will play"
        if out is sys.stdout:
            try:
                input("Enter to return to Studio... ")
            except (EOFError, KeyboardInterrupt):
                pass
