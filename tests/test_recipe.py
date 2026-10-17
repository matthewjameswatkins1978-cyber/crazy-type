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
    ],
)
def test_invalid_recipes_rejected(data):
    with pytest.raises(RecipeError):
        validate_recipe(data)


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
