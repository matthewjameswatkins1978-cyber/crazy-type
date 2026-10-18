"""CLI behaviour tests: input handling, JSON validity, errors, fallback."""

import io
import json
import re
import sys

import pytest

from crazy_type import cli, runner

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][AB0]")


def run_cli(monkeypatch, capsys, argv, stdin_text=None, tty=False):
    """Run cli.main with controlled TTY/stdin. Returns (code, out, err)."""
    monkeypatch.setattr(sys.stdout, "isatty", lambda: tty)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False if stdin_text is not None else True)
    if stdin_text is not None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_direct_input_plain_fallback(monkeypatch, capsys):
    code, out, _ = run_cli(monkeypatch, capsys, ["Hello world", "--plain"])
    assert code == 0
    assert out.strip() == "Hello world"
    assert ANSI_RE.search(out) is None


def test_piped_input_plain_fallback(monkeypatch, capsys):
    code, out, _ = run_cli(monkeypatch, capsys, ["--plain"], stdin_text="piped hello\n")
    assert code == 0
    assert out.strip() == "piped hello"


def test_non_tty_defaults_to_plain(monkeypatch, capsys):
    # Redirected output must never contain ANSI codes.
    code, out, _ = run_cli(monkeypatch, capsys, ["Hello"], tty=False)
    assert code == 0
    assert out.strip() == "Hello"
    assert ANSI_RE.search(out) is None


def test_cp1252_tty_falls_back_cleanly(monkeypatch, capsys):
    # A TTY whose encoding cannot render glyphs must get plain text,
    # not a UnicodeEncodeError traceback (seen on a default-CP ConPTY).
    import io as _io

    class Cp1252Out(_io.StringIO):
        encoding = "cp1252"

        def isatty(self):
            return True

    fake = Cp1252Out()
    monkeypatch.setattr(sys, "stdout", fake)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    code = cli.main(["hi", "--effect", "decrypt"])
    out, err = fake.getvalue(), capsys.readouterr().err
    assert code == 0
    assert out.strip() == "hi"
    assert "chcp 65001" in err


def test_no_input_is_usage_error(monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    code = cli.main([])
    captured = capsys.readouterr()
    assert code == 2
    assert "no input" in captured.err.lower()


def test_effects_json_valid_no_ansi(monkeypatch, capsys):
    code, out, _ = run_cli(monkeypatch, capsys, ["effects", "--json"])
    assert code == 0
    payload = json.loads(out)
    assert len(payload["effects"]) >= 10
    assert ANSI_RE.search(out) is None


def test_doctor_json_valid_no_ansi(monkeypatch, capsys):
    code, out, _ = run_cli(monkeypatch, capsys, ["doctor", "--json"])
    assert code == 0
    payload = json.loads(out)
    assert payload["crazytype"]
    assert payload["effects_count"] >= 10
    assert ANSI_RE.search(out) is None


def _run(monkeypatch, capsys, argv, tty=False):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: tty)
    return cli.main(argv), capsys.readouterr()


def test_routing_blocks_human_and_json(monkeypatch, capsys):
    code, cap = _run(monkeypatch, capsys, ["blocks"])
    assert code == 0 and "tte" in cap.out
    code, cap = _run(monkeypatch, capsys, ["blocks", "--json"])
    assert code == 0 and json.loads(cap.out)["recipe_format_version"] == 1


def test_routing_play_errors(monkeypatch, capsys):
    code, cap = _run(monkeypatch, capsys, ["play", "no-such-recipe"])
    assert code == 2 and "not found" in cap.err
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    code, cap = _run(monkeypatch, capsys, ["play", "giant-growth"])
    assert code == 2 and "no input" in cap.err


def test_routing_export_errors(monkeypatch, capsys):
    code, cap = _run(monkeypatch, capsys, ["export", "giant-growth", "Hi"])
    assert code == 2 and "--recipe" in cap.err
    code, cap = _run(monkeypatch, capsys, ["export", "nope", "Hi", "--recipe", "x.json"])
    assert code == 2


def test_routing_studio_bad_recipe(monkeypatch, capsys):
    code, cap = _run(monkeypatch, capsys, ["studio", "no-such-recipe"])
    assert code == 2


def test_routing_subcommand_help(monkeypatch, capsys):
    for argv in (["play", "--help"], ["studio", "--help"], ["export", "--help"],
                 ["blocks", "--help"], ["effects", "--help"]):
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, capsys, argv)
        assert exc.value.code == 0


def test_routing_dashdash_literal_text(monkeypatch, capsys):
    # `crazytype --plain -- effects` must animate the word, not list effects.
    code, out, _ = run_cli(monkeypatch, capsys, ["--plain", "--", "effects"])
    assert code == 0 and out.strip() == "effects"


def test_unknown_effect_suggests(monkeypatch, capsys):
    # Force a TTY so we reach effect resolution instead of the plain fallback,
    # but stub the player to resolve-then-succeed so no animation frames run.
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(
        "crazy_type.cli.play_animation",
        lambda text, name: (runner.resolve_effect(name), 0)[1],
    )
    code = cli.main(["hi", "--effect", "decript"])
    captured = capsys.readouterr()
    assert code == 2
    assert "unknown effect" in captured.err.lower()
    assert "decrypt" in captured.err.lower()


def test_resolve_effect_suggestion_quality():
    with pytest.raises(runner.UnknownEffectError) as exc:
        runner.resolve_effect("decript")
    assert "decrypt" in exc.value.suggestions


def test_figlet_renders_banner():
    banner = runner.apply_figlet("Hi", "slant")
    assert len(banner.splitlines()) > 1  # real ASCII art, not plain text


def test_figlet_bad_font():
    with pytest.raises(ValueError, match="unknown figlet font"):
        runner.apply_figlet("Hi", "no-such-font-xyz")


def test_auto_mode_announces_choice_on_stderr(monkeypatch, capsys):
    code, out, err = run_cli(monkeypatch, capsys, ["ERROR: disk gone", "--auto", "--plain"])
    assert code == 0
    assert "errorcorrect" in err
    assert out.strip() == "ERROR: disk gone"


def test_stdout_stays_composable(monkeypatch, capsys):
    # Ordinary program output on stdout; diagnostics only on stderr, never ANSI on stdout.
    code, out, err = run_cli(monkeypatch, capsys, ["hi", "--effect", "decrypt", "--plain"])
    assert code == 0
    assert out.strip() == "hi"
    assert ANSI_RE.search(out) is None
    assert ANSI_RE.search(err) is None


def test_real_engine_smoke_and_cleanup(capsys):
    # Actually render a tiny animation through the real TTE engine and
    # verify the terminal state is restored (cursor shown again).
    code = runner.play_animation("Hi", "print")
    assert code == 0
    out = capsys.readouterr().out
    assert "\x1b[?25h" in out  # show-cursor: terminal cleanup happened
    assert "H" in out and "i" in out


def test_demo_flow_quit_after_first(monkeypatch, capsys):
    # Drive the interactive demo: fake a TTY, answer 'q' at the first prompt.
    # Renders one real effect, then quits cleanly with cursor restored.
    from unittest import mock

    answers = iter(["q"])
    with (
        mock.patch.object(sys.stdout, "isatty", return_value=True),
        mock.patch("builtins.input", side_effect=lambda *a, **k: next(answers)),
    ):
        code = cli.cmd_demo()
    out = capsys.readouterr().out
    assert code == 0
    assert out.count("--- ") == 1
    assert "\x1b[?25h" in out
    assert "That's Crazy Type" in out


def test_demo_refuses_non_tty(monkeypatch, capsys):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    assert cli.cmd_demo() == 1
    assert "interactive terminal" in capsys.readouterr().err


def test_figlet_banner_animates(capsys):
    # A multi-line figlet banner must render through the real engine.
    banner = runner.apply_figlet("Hi", "slant")
    assert len(banner.splitlines()) > 1
    code = runner.play_animation(banner, "decrypt")
    assert code == 0
    out = capsys.readouterr().out
    assert "\x1b[?25h" in out
    assert "/" in out and "_" in out
