"""Shared fixtures: make animation-capability tests hermetic.

Many tests fake a TTY and then assert on the animated path. CI systems,
containers and odd developer shells set environment markers (CI=true,
NO_COLOR, dumb TERM, ...) that would flip should_animate() to the plain
fallback and make those tests pass for the wrong reason — or fail. Scrub
them for every test; individual tests re-set what they need.
"""

import os

import pytest

_SCRUBBED = (
    "CI",
    "CONTINUOUS_INTEGRATION",
    "GITHUB_ACTIONS",
    "GITLAB_CI",
    "JENKINS_URL",
    "TF_BUILD",
    "TEAMCITY_VERSION",
    "NO_COLOR",
    "REDUCED_MOTION",
    "PREFERS_REDUCED_MOTION",
    "CRAZYTYPE_REDUCED_MOTION",
    "CRAZYTYPE_PLAIN",
    "TERM",
)


@pytest.fixture(autouse=True)
def _hermetic_terminal_env(monkeypatch):
    for var in _SCRUBBED:
        monkeypatch.delenv(var, raising=False)
    # A sane terminal for tests that do not fake one themselves.
    monkeypatch.setenv("TERM", "xterm-256color")
