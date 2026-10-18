"""Terminal capability / plain-text fallback tests."""

import sys

import pytest

from crazy_type import terms


def _tty(monkeypatch, is_tty: bool):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: is_tty)


@pytest.mark.parametrize("marker", ["CI", "GITHUB_ACTIONS", "TF_BUILD"])
def test_ci_forces_plain(monkeypatch, marker, capsys):
    _tty(monkeypatch, True)
    monkeypatch.setenv(marker, "true")
    animate, reason = terms.should_animate()
    assert animate is False
    assert "CI" in reason or "detected" in reason


def test_redirected_output_forces_plain(monkeypatch):
    _tty(monkeypatch, False)
    animate, reason = terms.should_animate()
    assert animate is False
    assert "redirect" in reason


def test_no_color_forces_plain(monkeypatch):
    _tty(monkeypatch, True)
    monkeypatch.setenv("NO_COLOR", "1")
    animate, _ = terms.should_animate()
    assert animate is False


def test_reduced_motion_forces_plain(monkeypatch):
    _tty(monkeypatch, True)
    monkeypatch.setenv("REDUCED_MOTION", "1")
    animate, _ = terms.should_animate()
    assert animate is False


def test_dumb_terminal_forces_plain(monkeypatch):
    _tty(monkeypatch, True)
    monkeypatch.setenv("TERM", "dumb")
    animate, _ = terms.should_animate()
    assert animate is False


def test_force_plain_flag(monkeypatch):
    _tty(monkeypatch, True)
    animate, _ = terms.should_animate(force_plain=True)
    assert animate is False


def test_glyph_probe_utf8_passes():
    ok, _ = terms.console_supports_glyphs()
    assert ok is True  # pytest capture is UTF-8


def test_glyph_probe_rejects_ascii(monkeypatch):
    class AsciiOut:
        encoding = "ascii"

        def isatty(self):
            return True

        def write(self, s):
            return len(s)

        def flush(self):
            pass

    monkeypatch.setattr(sys, "stdout", AsciiOut())
    ok, encoding = terms.console_supports_glyphs()
    assert ok is False
    animate, reason = terms.should_animate()
    assert animate is False
    assert "chcp 65001" in reason


def test_healthy_terminal_animates(monkeypatch):
    _tty(monkeypatch, True)
    for var in ("CI", "GITHUB_ACTIONS", "TF_BUILD", "NO_COLOR", "REDUCED_MOTION",
                "PREFERS_REDUCED_MOTION", "CRAZYTYPE_REDUCED_MOTION",
                "CONTINUOUS_INTEGRATION", "GITLAB_CI", "JENKINS_URL",
                "TEAMCITY_VERSION", "CONTINUOUS_INTEGRATION"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    animate, _ = terms.should_animate()
    assert animate is True


def test_terminal_width_fallback(monkeypatch):
    import shutil

    monkeypatch.setattr(shutil, "get_terminal_size", lambda fallback: (_ for _ in ()).throw(OSError()))
    assert terms.terminal_width() == 80


def test_restore_cursor_never_raises(monkeypatch, capsys):
    _tty(monkeypatch, True)
    terms.restore_cursor()  # must not raise
