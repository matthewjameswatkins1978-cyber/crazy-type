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
    assert blank_recipe()["blocks"][0]["kind"] == "hold"


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
