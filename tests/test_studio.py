"""Studio tests: model edits, undo/redo, validation, headless screen driving."""

import io
import json

import pytest

from crazy_type.recipe import validate_recipe
from crazy_type.studio import Studio, blank_recipe, block_summary, render, run_studio


def make_state():
    return Studio(
        validate_recipe(
            {
                "format_version": 1,
                "name": "t",
                "blocks": [
                    {"kind": "tte", "effect": "decrypt"},
                    {"kind": "hold", "seconds": 1.0},
                ],
            }
        )
    )


def test_blank_recipe_valid():
    recipe = blank_recipe()
    assert recipe["blocks"][0]["kind"] == "tte"  # first preview must show something


def test_add_remove_move_duplicate():
    st = make_state()
    st.add_block({"kind": "ambient", "duration_seconds": 5.0, "fps": 10, "seed": None})
    assert [b["kind"] for b in st.recipe["blocks"]] == ["tte", "ambient", "hold"]
    st.move_selected(-1)
    assert [b["kind"] for b in st.recipe["blocks"]] == ["ambient", "tte", "hold"]
    st.duplicate_selected()
    assert len(st.recipe["blocks"]) == 4
    st.remove_selected()
    assert len(st.recipe["blocks"]) == 3


def test_cannot_remove_last_block():
    st = Studio(blank_recipe())
    st.remove_selected()
    assert len(st.recipe["blocks"]) == 1
    assert "at least one" in st.status


def test_undo_redo_roundtrip():
    st = make_state()
    before = [b["kind"] for b in st.recipe["blocks"]]
    st.remove_selected()
    assert [b["kind"] for b in st.recipe["blocks"]] != before
    st.undo()
    assert [b["kind"] for b in st.recipe["blocks"]] == before
    st.redo()
    assert len(st.recipe["blocks"]) == len(before) - 1
    st.undo()
    st.undo()  # nothing left: status, not a crash
    assert "nothing to undo" in st.status


def test_set_param_validated():
    st = make_state()
    st.selected = 1
    st.set_param("seconds", "2.5")
    assert st.recipe["blocks"][1]["seconds"] == 2.5
    st.set_param("seconds", "banana")
    assert st.recipe["blocks"][1]["seconds"] == 2.5
    assert "error" in st.status


def test_save_and_reload(tmp_path):
    st = make_state()
    target = tmp_path / "mine.json"
    st.save(str(target))
    assert "saved to" in st.status
    assert json.loads(target.read_text(encoding="utf-8"))["name"] == "t"


def test_block_summary_covers_kinds():
    assert "decrypt" in block_summary({"kind": "tte", "effect": "decrypt", "mode": "stacked", "params": {}})
    assert "hold" in block_summary({"kind": "hold", "seconds": 1.0})
    assert "ambient" in block_summary({"kind": "ambient", "duration_seconds": 1.0, "fps": 10})
    assert "grow" in block_summary({"kind": "grow", "fonts": ["mini"], "end": "word"})


def test_headless_drive_add_and_quit():
    # Drive the editor with injected keys: add an ambient block, quit.
    st = make_state()
    out = io.StringIO()
    code = run_studio(st, keys=["a", "down", "down", "enter", "q"], out=out, size=(100, 30))
    assert code == 0
    assert [b["kind"] for b in st.recipe["blocks"]] == ["tte", "ambient", "hold"]
    text = out.getvalue()
    assert "Crazy Type Studio" in text
    assert "\x1b[?1049l" in text  # alt screen exited
    assert "\x1b[?25h" in text  # cursor restored


def test_headless_drive_edit_param_and_undo():
    st = make_state()
    out = io.StringIO()
    # a/add ambient, esc? flow: add ambient (down,enter), then undo, quit.
    code = run_studio(st, keys=["a", "down", "enter", "u", "q"], out=out, size=(100, 30))
    assert code == 0
    assert [b["kind"] for b in st.recipe["blocks"]] == ["tte", "hold"]


def test_render_never_leaks_raw_text():
    st = make_state()
    out = io.StringIO()
    for screen in ("blocks", "edit", "add", "effect", "help"):
        st.screen = screen
        render(st, out, 100, 30)
    assert "Crazy Type Studio" in out.getvalue()


def test_q_backs_out_of_subscreens():
    from crazy_type.studio import handle_key

    st = make_state()
    out = io.StringIO()
    for screen in ("edit", "add", "effect", "help"):
        st.screen = screen
        assert handle_key(st, "q", out) is None  # backs out, never quits
        assert st.screen == "blocks"
    st.screen = "blocks"
    assert handle_key(st, "q", out) == "quit"  # clean state quits at once


def test_dirty_quit_arms_then_confirms():
    from crazy_type.studio import handle_key

    st = make_state()
    out = io.StringIO()
    st.remove_selected()  # dirty now
    assert handle_key(st, "q", out) is None  # arms, does not quit
    assert "UNSAVED" in st.status
    assert handle_key(st, "q", out) == "quit"  # second q discards + quits


def test_dirty_quit_disarms():
    from crazy_type.studio import handle_key

    st = make_state()
    out = io.StringIO()
    st.remove_selected()
    assert handle_key(st, "q", out) is None
    assert handle_key(st, "esc", out) is None
    assert st.quit_armed is False
    assert handle_key(st, "q", out) is None  # arms again
    assert handle_key(st, "j", out) is None  # any other key disarms
    assert st.quit_armed is False


def test_effect_picker_retargets_existing_block():
    from crazy_type.studio import handle_key

    st = make_state()  # block 0 = tte decrypt
    out = io.StringIO()
    assert handle_key(st, "enter", out) is None  # blocks -> edit
    # Move to the 'effect' param and confirm -> effect picker in edit mode.
    assert handle_key(st, "enter", out) is None
    assert st.screen == "effect"
    assert st.effect_target == "edit"
    st.effect_filter = "matrix"
    assert handle_key(st, "enter", out) is None
    assert st.screen == "blocks"
    assert st.recipe["blocks"][0]["effect"] == "matrix"


def test_param_hint_mentions_range_and_current():
    from crazy_type.studio import param_hint

    hint = param_hint({"type": (int, float), "range": (0.1, 300.0)}, 1.0)
    assert "0.1-300" in hint and "1.0" in hint


def test_prompt_line_types_backspaces_confirms(monkeypatch):
    import crazy_type.studio as studio_mod

    keys = iter(["h", "i", "backspace", "!", "enter"])
    monkeypatch.setattr(studio_mod, "read_key", lambda: next(keys))
    out = io.StringIO()
    assert studio_mod.prompt_line("Name: ", out) == "h!"
    assert "Name: h!" in out.getvalue()


def test_prompt_line_esc_cancels_to_empty(monkeypatch):
    import crazy_type.studio as studio_mod

    keys = iter(["x", "y", "esc"])
    monkeypatch.setattr(studio_mod, "read_key", lambda: next(keys))
    assert studio_mod.prompt_line("Name: ", io.StringIO()) == ""


def test_prompt_line_ctrl_c_cancels(monkeypatch):
    import crazy_type.studio as studio_mod

    keys = iter(["a", "\x03"])
    monkeypatch.setattr(studio_mod, "read_key", lambda: next(keys))
    assert studio_mod.prompt_line("Name: ", io.StringIO()) == ""


def test_blocks_key_dispatch(monkeypatch, tmp_path):
    import crazy_type.studio as sm
    from crazy_type.studio import handle_key

    st = make_state()  # [tte decrypt, hold]
    out = io.StringIO()
    target = tmp_path / "s-as.json"
    answers = iter(["Hey", "Zed", "giant-growth", str(target)])
    monkeypatch.setattr(sm, "prompt_line", lambda *a, **k: next(answers))
    kinds = lambda: [b["kind"] for b in st.recipe["blocks"]]
    assert handle_key(st, "d", out) is None and kinds() == ["tte", "tte", "hold"]
    assert handle_key(st, "x", out) is None and kinds() == ["tte", "hold"]
    assert handle_key(st, "K", out) is None and kinds() == ["hold", "tte"]
    assert handle_key(st, "J", out) is None and kinds() == ["tte", "hold"]
    assert handle_key(st, "u", out) is None and kinds() == ["hold", "tte"]
    assert handle_key(st, "r", out) is None and kinds() == ["tte", "hold"]
    assert handle_key(st, "m", out) is None and st.message == "Hey"
    assert handle_key(st, "n", out) is None and st.recipe["name"] == "Zed"
    assert handle_key(st, "o", out) is None and st.recipe["name"] == "giant-growth"
    assert handle_key(st, "S", out) is None and target.exists()
    assert handle_key(st, "p", out) == "play"


def test_run_studio_refuses_small_terminal():
    st = make_state()
    assert run_studio(st, keys=["q"], out=io.StringIO(), size=(30, 10)) == 1


def test_run_studio_refuses_non_interactive_stdin(monkeypatch):
    import sys

    st = make_state()
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert run_studio(st, out=io.StringIO(), size=(100, 30)) == 1


def test_run_studio_keyboard_interrupt_exits_130():
    class Boom:
        def __iter__(self):
            return self

        def __next__(self):
            raise KeyboardInterrupt()

    st = make_state()
    assert run_studio(st, keys=Boom(), out=io.StringIO(), size=(100, 30)) == 130


def test_run_studio_play_key_plays_and_returns():
    st = make_state()
    out = io.StringIO()
    assert run_studio(st, keys=["p", "q"], out=out, size=(100, 30)) == 0
    assert "exactly what the CLI will play" in st.status


def test_effect_picker_filter_and_select():
    from crazy_type.studio import handle_key

    st = make_state()  # [tte decrypt, hold]
    out = io.StringIO()
    assert handle_key(st, "a", out) is None
    assert handle_key(st, "enter", out) is None  # tte -> picker
    assert st.screen == "effect"
    for ch in "mat":
        assert handle_key(st, ch, out) is None
    assert st.effect_filter == "mat"
    assert handle_key(st, "backspace", out) is None
    assert st.effect_filter == "ma"
    for ch in "trix":
        assert handle_key(st, ch, out) is None
    assert handle_key(st, "enter", out) is None
    assert st.screen == "blocks"
    added = st.recipe["blocks"][1]
    assert added["kind"] == "tte" and added["effect"] == "matrix"


def test_parse_param_shapes():
    from crazy_type.recipe import RecipeError
    from crazy_type.studio import _parse_param

    assert _parse_param({"type": dict}, '{"a": 1}') == {"a": 1}
    with pytest.raises(RecipeError):
        _parse_param({"type": dict}, "{oops")
    with pytest.raises(RecipeError):
        _parse_param({"type": dict}, "[1, 2]")
    assert _parse_param({"type": list}, "mini, standard") == ["mini", "standard"]
    assert _parse_param({"type": int}, "5") == 5
    with pytest.raises(RecipeError):
        _parse_param({"type": int}, "x")
    assert _parse_param({"type": (int, float)}, "2.5") == 2.5
    assert _parse_param({"type": (int, float)}, "3") == 3
    assert _parse_param({"type": (int, float), "required": False, "default": 1.0}, "") == 1.0
    with pytest.raises(RecipeError):
        _parse_param({"type": (int, float)}, "x")


def test_open_recipe_by_builtin_name_path_and_error(monkeypatch, tmp_path):
    import crazy_type.studio as studio_mod

    st = make_state()
    out = io.StringIO()
    monkeypatch.setattr(studio_mod, "prompt_line", lambda *a, **k: "giant-growth")
    studio_mod.open_recipe(st, out)
    assert st.recipe["name"] == "giant-growth"
    assert st.path is None  # bundled names are not save destinations
    assert st.dirty is False
    real = tmp_path / "mine.json"
    real.write_text(
        '{"format_version": 1, "name": "mine", '
        '"blocks": [{"kind": "hold", "seconds": 1}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(studio_mod, "prompt_line", lambda *a, **k: str(real))
    studio_mod.open_recipe(st, out)
    assert st.recipe["name"] == "mine"
    assert st.path == str(real)  # real user files stay as save destinations
    monkeypatch.setattr(studio_mod, "prompt_line", lambda *a, **k: "/nonexistent/xyz.json")
    studio_mod.open_recipe(st, out)
    assert "error" in st.status
    assert st.recipe["name"] == "mine"  # failed open keeps current
    monkeypatch.setattr(studio_mod, "prompt_line", lambda *a, **k: "")
    studio_mod.open_recipe(st, out)  # blank answer: no-op
    assert st.recipe["name"] == "mine"


def test_play_in_studio_reports_finished():
    from crazy_type.studio import play_in_studio

    st = make_state()
    out = io.StringIO()
    play_in_studio(st, out)  # headless: plain fallback, no pause (out is not stdout)
    assert "exactly what the CLI will play" in st.status


def test_stale_param_index_clamped_no_crash():
    # Edit a 3-param block at index 2, move to a 1-param block, press enter:
    # must clamp to 'seconds', not IndexError.
    import crazy_type.studio as studio_mod

    from crazy_type.studio import handle_key

    st = make_state()  # [tte decrypt, hold]
    out = io.StringIO()
    st.selected = 1  # hold block: only 'seconds'
    st.screen = "edit"
    st.param_index = 2  # stale: left over from the tte block
    orig = studio_mod.prompt_line
    studio_mod.prompt_line = lambda *a, **k: "3.5"
    try:
        assert handle_key(st, "enter", out) is None
    finally:
        studio_mod.prompt_line = orig
    assert st.recipe["blocks"][1]["seconds"] == 3.5


def test_remix_save_play_roundtrip(tmp_path):
    """End-to-end acceptance: remix in Studio with keys only, save, play via CLI path."""
    import re
    import sys
    from unittest import mock

    from crazy_type.cli import _builtin_or_path, cmd_play
    from crazy_type.recipe import load_recipe

    target = tmp_path / "remix.json"
    loaded = load_recipe(_builtin_or_path("living-neon"))
    loaded["blocks"][0]["duration_seconds"] = 1.0  # keep the test fast; remix doubles it
    st = Studio(loaded)
    st.message = "Remix"
    st.path = str(target)
    out = io.StringIO()
    code = run_studio(st, keys=["d", "s", "q"], out=out, size=(100, 30))
    assert code == 0
    reloaded = load_recipe(str(target))
    assert len(reloaded["blocks"]) == 2  # duplicated ambient
    buf = io.StringIO()
    with mock.patch.object(buf, "isatty", return_value=True):
        with mock.patch.object(sys, "stdout", buf):
            play_code = cmd_play(str(target), "Remix")
    assert play_code == 0
    assert "\x1b[?25h" in buf.getvalue()
    plain = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", buf.getvalue())
    assert "Remix" in plain
