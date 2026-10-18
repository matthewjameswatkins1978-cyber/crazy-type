"""Export tests: recipe envelope and asciicast recording round trips."""

import json

from crazy_type.cli import _builtin_or_path
from crazy_type.export import CastWriter, export_recipe
from crazy_type.recipe import load_recipe


def test_export_recipe_file(tmp_path):
    target = tmp_path / "out.json"
    code = export_recipe(load_recipe(_builtin_or_path("living-neon")), "Hi", str(target), None)
    assert code == 0
    reloaded = load_recipe(str(target))
    assert reloaded["name"] == "living-neon"


def test_export_prints_recipe_when_no_paths(capsys):
    code = export_recipe(load_recipe(_builtin_or_path("giant-growth")), "Hi", None, None)
    assert code == 0
    assert json.loads(capsys.readouterr().out)["format_version"] == 1


def test_export_cast_records_paced_animation(tmp_path):
    target = tmp_path / "rec.cast"
    recipe = load_recipe(_builtin_or_path("particle-reconstruction"))
    code = export_recipe(recipe, "BAM", None, str(target))
    assert code == 0
    lines = target.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    assert header["version"] == 2
    events = [json.loads(line) for line in lines[1:]]
    assert len(events) > 10
    assert events[-1][0] > 1.0  # real pacing captured, not instant
    assert all(ev[1] == "o" for ev in events)
    assert any("?25h" in ev[2] for ev in events)  # cursor restore recorded


def test_export_invalid_recipe_rejected(capsys):
    assert export_recipe({"bogus": 1}, "Hi", "x.json", None) == 2
    assert "error" in capsys.readouterr().err


def test_export_unwritable_paths(capsys, tmp_path):
    # A missing parent directory is unwritable on every platform (a bare
    # "Z:\..." name is a legal filename on POSIX, so it proves nothing).
    bad = str(tmp_path / "no-such-dir" / "out.json")
    recipe = load_recipe(_builtin_or_path("living-neon"))
    assert export_recipe(recipe, "Hi", bad, None) == 1
    assert export_recipe(recipe, "Hi", None, bad) == 1
    assert "cannot write" in capsys.readouterr().err


def test_cast_writer_flushes_handle():
    from unittest import mock

    from crazy_type.export import CastWriter

    handle = mock.Mock()
    CastWriter(handle, 80, 24).flush()
    handle.flush.assert_called_once_with()


def test_cast_writer_event_shape(tmp_path):
    target = tmp_path / "w.cast"
    with open(target, "w", encoding="utf-8") as handle:
        writer = CastWriter(handle, 80, 24)
        writer.write("hi")
        writer.write("")
        writer.flush()
    lines = target.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["version"] == 2
    assert len(lines) == 2  # empty writes record nothing
