"""Recipe format tests: parsing, validation, config building, catalogue."""

import json

import pytest

from crazy_type import recipe
from crazy_type.recipe import RecipeError, block_catalogue, load_recipe, validate_recipe


def good_recipe(**overrides):
    data = {
        "format_version": 1,
        "name": "demo",
        "blocks": [{"kind": "hold", "seconds": 1.0}],
    }
    data.update(overrides)
    return data


def test_valid_recipe_normalizes_defaults():
    out = validate_recipe(good_recipe(blocks=[{"kind": "ambient", "duration_seconds": 5.0}]))
    assert out["blocks"][0]["fps"] == 10
    assert out["format_version"] == 1


def test_all_block_kinds_validate():
    out = validate_recipe(
        good_recipe(
            blocks=[
                {"kind": "tte", "effect": "decrypt"},
                {"kind": "hold", "seconds": 0.5},
                {"kind": "ambient", "duration_seconds": 3.0},
                {"kind": "grow", "fonts": ["mini"]},
            ]
        )
    )
    assert [b["kind"] for b in out["blocks"]] == ["tte", "hold", "ambient", "grow"]
    assert out["blocks"][0]["mode"] == "stacked"
    assert out["blocks"][0]["params"] == {}


@pytest.mark.parametrize(
    "data",
    [
        {"format_version": 2, "name": "x", "blocks": [{"kind": "hold", "seconds": 1}]},
        {"format_version": 1, "name": "", "blocks": [{"kind": "hold", "seconds": 1}]},
        {"format_version": 1, "name": "x", "blocks": []},
        {"format_version": 1, "name": "x", "blocks": [{"kind": "nope"}]},
        {"format_version": 1, "name": "x", "blocks": [{"kind": "hold"}]},
        {"format_version": 1, "name": "x", "blocks": [{"kind": "hold", "seconds": 0}]},
        {"format_version": 1, "name": "x", "blocks": [{"kind": "hold", "seconds": 1, "extra": 1}]},
        {"format_version": 1, "name": "x", "blocks": [{"kind": "tte", "effect": "nope"}]},
        {"format_version": 1, "name": "x", "blocks": [], "bogus": 1},
        {"format_version": 1, "name": "x", "blocks": [{"kind": "ambient", "duration_seconds": 0.5}]},
        {"format_version": 1, "name": "x", "blocks": [{"kind": "grow", "fonts": []}]},
        {"format_version": 1, "name": "x", "blocks": [{"kind": "grow", "end": "sideways"}]},
        {"format_version": 1, "name": "x", "blocks": "hold"},
        {"format_version": 1, "name": "x", "blocks": ["hold"]},
        {"format_version": 1, "name": "x", "seed": "seven", "blocks": [{"kind": "hold", "seconds": 1}]},
        {"format_version": 1, "name": "x", "description": 42, "blocks": [{"kind": "hold", "seconds": 1}]},
        {"format_version": 1, "name": "x", "capabilities": "color", "blocks": [{"kind": "hold", "seconds": 1}]},
        {"format_version": 1, "name": "x", "blocks": [{"kind": "hold", "seconds": True}]},
    ],
)
def test_invalid_recipes_rejected(data):
    with pytest.raises(RecipeError):
        validate_recipe(data)


def test_validate_block_rejects_bad_collections():
    from crazy_type.recipe import validate_block
    from crazy_type.recipe import RecipeError

    with pytest.raises(RecipeError):
        validate_block(0, {"kind": "tte", "effect": "decrypt", "params": {1: "x"}})
    with pytest.raises(RecipeError):
        validate_block(0, {"kind": "grow", "fonts": []})
    with pytest.raises(RecipeError):
        validate_block(0, {"kind": "grow", "fonts": [1, 2]})
    with pytest.raises(RecipeError):
        validate_block(0, {"kind": "tte", "effect": "decrypt", "params": ["x"]})


def test_layers_reserved_empty_ok_nonempty_rejected():
    ok = validate_recipe(good_recipe(layers=[]))
    assert ok["layers"] == []
    with pytest.raises(RecipeError, match="later milestone"):
        validate_recipe(good_recipe(layers=[{"kind": "ambient"}]))
    with pytest.raises(RecipeError):
        validate_recipe(good_recipe(layers="nope"))


def test_catalogue_declares_no_layers():
    assert block_catalogue()["layers_supported"] is False


def test_load_from_json_string_and_dict():
    data = good_recipe()
    assert load_recipe(data)["name"] == "demo"
    assert load_recipe(json.dumps(data))["name"] == "demo"


def test_load_missing_file_and_bad_json():
    with pytest.raises(RecipeError, match="not found"):
        load_recipe("no-such-recipe.json")
    with pytest.raises(RecipeError, match="not valid JSON"):
        load_recipe("{oops")


def test_effect_config_defaults_and_overrides():
    cfg = recipe.build_effect_config("decrypt", {})
    assert cfg.typing_speed == 2
    cfg = recipe.build_effect_config("decrypt", {"typing-speed": 5})
    assert cfg.typing_speed == 5


def test_effect_config_rejects_bad_params():
    with pytest.raises(RecipeError):
        recipe.build_effect_config("decrypt", {"nope": 1})
    with pytest.raises(RecipeError):
        recipe.build_effect_config("no-such-fx", {})
    with pytest.raises(RecipeError, match="invalid params"):
        recipe.build_effect_config("decrypt", {"typing-speed": 0})


def test_effect_config_bool_and_list_shapes():
    cfg = recipe.build_effect_config("bubbles", {"rainbow": True})
    assert cfg.rainbow is True
    cfg = recipe.build_effect_config("bubbles", {"rainbow": False})
    assert cfg.rainbow is False
    cfg = recipe.build_effect_config("decrypt", {"ciphertext-colors": ["00ff00", "ff0000"]})
    assert len(cfg.ciphertext_colors) == 2


def test_block_catalogue_json_safe():
    catalogue = block_catalogue()
    text = json.dumps(catalogue)
    assert catalogue["recipe_format_version"] == 1
    assert set(catalogue["blocks"]) == {"tte", "hold", "ambient", "grow"}
    assert len(catalogue["tte_effects"]) >= 10
    assert "\x1b" not in text


def _play_headless(monkeypatch, capsys, recipe_data, text):
    """Play a recipe with a faked TTY; return (code, stripped_output)."""
    import io
    import re
    import sys
    from unittest import mock

    from crazy_type.runtime import play_recipe

    buf = io.StringIO()
    with mock.patch.object(buf, "isatty", return_value=True):
        with mock.patch.object(sys, "stdout", buf):
            code = play_recipe(recipe_data, text)
    out = buf.getvalue()
    plain = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][AB0]|\x1b[78]", "", out)
    return code, out, plain


def test_giant_growth_ends_on_word(monkeypatch, capsys):
    # Play the real bundled recipe through cmd_play with a faked TTY.
    import io
    import re
    import sys
    from unittest import mock

    from crazy_type.cli import cmd_play

    buf = io.StringIO()
    with mock.patch.object(buf, "isatty", return_value=True):
        with mock.patch.object(sys, "stdout", buf):
            code = cmd_play("giant-growth", "GROW")
    out = buf.getvalue()
    assert code == 0
    assert "\x1b[?25h" in out  # cursor restored
    assert "GROW" in re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", out)


def test_ambient_settles_readable(monkeypatch, capsys):
    data = {
        "format_version": 1,
        "name": "t",
        "blocks": [{"kind": "ambient", "duration_seconds": 1.0, "fps": 20, "seed": 5}],
    }
    code, out, plain = _play_headless(monkeypatch, capsys, recipe.validate_recipe(data), "Neon")
    assert code == 0
    assert "\x1b[?25h" in out
    assert "Neon" in plain
    assert "\x1b" not in plain  # settled text is cleanly readable


def test_grow_unknown_font_rejected():
    from crazy_type.runtime import Pipeline

    pipe = Pipeline()
    with pytest.raises(RecipeError, match="unknown figlet font"):
        pipe.run_grow("Hi", ["no-such-font"], 0.0, "word")


def test_grow_clear_leaves_no_word(capsys):
    from crazy_type.runtime import Pipeline

    import re

    pipe = Pipeline()
    pipe.run_grow("GROW", ["mini"], 0.0, "clear")
    out = capsys.readouterr().out
    plain = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", out)
    assert "GROW" not in plain.split()  # final word line wiped, art cleared


def test_grow_falls_back_when_nothing_fits(capsys):
    from crazy_type.runtime import Pipeline

    pipe = Pipeline()
    pipe.width = 10  # narrower than even the mini FIGlet stage
    pipe.height = 10
    pipe.run_grow("GROW", ["mini", "standard", "big"], 0.0, "word")
    out = capsys.readouterr().out
    assert "GROW" in out
    assert "\x1b" not in out  # plain print, no half-drawn art


def test_terminal_size_clamps_minimums(monkeypatch):
    import shutil
    from types import SimpleNamespace

    from crazy_type.runtime import terminal_size

    monkeypatch.setattr(
        shutil, "get_terminal_size", lambda fallback: SimpleNamespace(columns=5, lines=5)
    )
    assert terminal_size() == (20, 10)


def test_play_interrupt_restores_cursor(monkeypatch, capsys):
    # Ctrl+C mid-recipe must exit 130 with the cursor shown again.
    from crazy_type import terms
    from crazy_type.runtime import Pipeline, play_recipe

    monkeypatch.setattr(terms, "should_animate", lambda force_plain=False: (True, "test"))
    monkeypatch.setattr(Pipeline, "run_hold", lambda self, s: (_ for _ in ()).throw(KeyboardInterrupt()))
    data = recipe.validate_recipe(good_recipe())
    assert play_recipe(data, "Hi") == 130
    assert "\x1b[?25h" in capsys.readouterr().out


def test_play_rejects_unknown_kind_defensively(monkeypatch, capsys):
    from crazy_type import terms
    from crazy_type.runtime import play_recipe

    monkeypatch.setattr(terms, "should_animate", lambda force_plain=False: (True, "test"))
    data = recipe.validate_recipe(good_recipe())
    data["blocks"].append({"kind": "teleport"})  # bypassed validation: must still fail safe
    with pytest.raises(RecipeError):
        play_recipe(data, "Hi")


def test_pipeline_pace_smoke():
    from crazy_type.runtime import Pipeline

    pipe = Pipeline(fps_cap=0)
    pipe.pace()  # disabled cap: instant no-op
    pipe = Pipeline(fps_cap=60)
    pipe.pace()
    pipe.pace()  # paced: no crash, timestamp advances
    assert pipe._last_frame > 0


def test_ambient_glitch_actually_renders(capsys):
    # Headline living-neon feature: at 30fps/3s the seeded glitch (frames
    # 30-70) must fire at least once. Proves corruption + recovery visibly.
    from crazy_type.runtime import GLITCH_COLOR, Pipeline

    pipe = Pipeline()
    pipe.run_ambient("Neon nights", 3.0, 30, seed=11)
    out = capsys.readouterr().out
    r, g, b = GLITCH_COLOR
    assert f"38;2;{r};{g};{b}" in out


def test_ambient_no_color_degrades_to_hold(monkeypatch, capsys):
    from crazy_type.runtime import Pipeline

    monkeypatch.setenv("NO_COLOR", "1")
    Pipeline().run_ambient("Neon", 0.2, 10, seed=None)
    out = capsys.readouterr().out
    assert out.strip() == "Neon"  # readable text, zero ANSI
    assert "\x1b" not in out


def test_play_rejects_foreign_format(capsys):
    from crazy_type.runtime import play_recipe

    assert play_recipe({"format_version": 999, "blocks": []}, "Hi") == 2
    assert "unsupported recipe format" in capsys.readouterr().err


def test_load_rejects_array_and_unknown_top_level():
    with pytest.raises(RecipeError, match="must be a JSON object"):
        load_recipe("[1, 2]")
    data = good_recipe()
    data["bogus"] = 1
    with pytest.raises(RecipeError, match="unknown top-level"):
        validate_recipe(data)


def test_play_plain_fallback_prints_text(monkeypatch, capsys):
    # Non-TTY recipe playback: plain text on stdout, note on stderr, exit 0.
    import io
    import sys
    from unittest import mock

    from crazy_type.runtime import play_recipe

    buf = io.StringIO()  # StringIO.isatty() is False -> redirected
    with mock.patch.object(sys, "stdout", buf):
        code = play_recipe(recipe.validate_recipe(good_recipe()), "Hello")
    assert code == 0
    assert buf.getvalue().strip() == "Hello"
    assert "plain text" in capsys.readouterr().err


def test_terminal_size_failure_falls_back(monkeypatch):
    import shutil

    from crazy_type.runtime import terminal_size

    def boom(fallback):
        raise OSError("no terminal")

    monkeypatch.setattr(shutil, "get_terminal_size", boom)
    assert terminal_size() == (80, 24)


def test_tte_inplace_reuses_region(monkeypatch, capsys):
    # In-place sequencing (ADR-1): the second block reuses the same screen
    # region instead of stacking below. Headless proof: final text present,
    # cursor restored, clean exit.
    data = {
        "format_version": 1,
        "name": "t",
        "blocks": [
            {"kind": "tte", "effect": "print", "mode": "inplace"},
            {"kind": "tte", "effect": "print", "mode": "inplace"},
        ],
    }
    code, out, plain = _play_headless(monkeypatch, capsys, recipe.validate_recipe(data), "Hi")
    assert code == 0
    assert "\x1b[?25h" in out
    assert "Hi" in plain


def test_tte_sequence_stacks(monkeypatch, capsys):
    data = {
        "format_version": 1,
        "name": "t",
        "blocks": [
            {"kind": "tte", "effect": "print", "mode": "stacked"},
            {"kind": "hold", "seconds": 0.1},
            {"kind": "tte", "effect": "print", "mode": "stacked"},
        ],
    }
    code, out, plain = _play_headless(monkeypatch, capsys, recipe.validate_recipe(data), "Hi")
    assert code == 0
    assert plain.count("Hi") >= 2  # both blocks left their final frames stacked
