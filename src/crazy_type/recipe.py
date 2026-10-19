"""Portable Recipe format (v1): declarative, validated, JSON.

A Recipe describes an effect independently of any editor. Text content is
supplied at playback, so one recipe animates many messages. Recipes are safe
declarative data — never executable code.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

RECIPE_FORMAT_VERSION = 1

# Block catalogue: kind -> parameter spec. Each param: (type, required, default, rule).
# Rules are (min, max) for numbers, or a set of allowed values for enums.
BLOCK_SPECS: dict[str, dict[str, Any]] = {
    "tte": {
        "help": "Play one installed TerminalTextEffects effect.",
        "params": {
            "effect": {"type": str, "required": True, "values": None},
            "params": {"type": dict, "required": False, "default": {}},
            "mode": {"type": str, "required": False, "default": "stacked", "values": ("stacked", "inplace")},
        },
    },
    "hold": {
        "help": "Pause on the current screen for a fixed time.",
        "params": {
            "seconds": {"type": (int, float), "required": True, "range": (0.1, 300.0)},
        },
    },
    "ambient": {
        "help": "Living text: gentle shimmer plus rare glitches, looping until duration or Ctrl+C.",
        "params": {
            "duration_seconds": {"type": (int, float), "required": True, "range": (1.0, 600.0)},
            "fps": {"type": int, "required": False, "default": 10, "range": (1, 30)},
            "seed": {"type": int, "required": False, "default": None},
        },
    },
    "grow": {
        "help": "Giant growth: word expands through FIGlet sizes, holds, then shrinks back.",
        "params": {
            "fonts": {
                "type": list, "required": False,
                "default": ["mini", "standard", "big"],
            },
            "hold_seconds": {"type": (int, float), "required": False, "default": 0.5, "range": (0.0, 30.0)},
            "end": {"type": str, "required": False, "default": "word", "values": ("word", "clear")},
        },
    },
}


class RecipeError(ValueError):
    """Raised when a recipe is invalid, with a message aimed at the author."""


def _check_number(value: Any, low: float, high: float, what: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecipeError(f"{what} must be a number, got {value!r}.")
    if not (low <= value <= high):
        raise RecipeError(f"{what} must be between {low} and {high}, got {value!r}.")


def validate_block(index: int, block: Any) -> dict[str, Any]:
    """Validate one block dict; return a normalized copy or raise RecipeError."""
    if not isinstance(block, dict):
        raise RecipeError(f"block {index}: must be an object, got {block!r}.")
    kind = block.get("kind")
    if kind not in BLOCK_SPECS:
        known = ", ".join(sorted(BLOCK_SPECS))
        raise RecipeError(f"block {index}: unknown kind {kind!r}. Known kinds: {known}.")
    spec = BLOCK_SPECS[kind]["params"]
    extra = set(block) - {"kind", *spec}
    if extra:
        raise RecipeError(f"block {index} ({kind}): unknown fields: {sorted(extra)}.")
    normalized: dict[str, Any] = {"kind": kind}
    for name, pspec in spec.items():
        if name not in block or block[name] is None:
            if pspec.get("required"):
                raise RecipeError(f"block {index} ({kind}): missing required field {name!r}.")
            normalized[name] = pspec.get("default")
            continue
        value = block[name]
        expected = pspec["type"]
        if expected is dict:
            if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
                raise RecipeError(f"block {index} ({kind}): {name!r} must be an object of string keys.")
        elif expected is list:
            if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
                raise RecipeError(f"block {index} ({kind}): {name!r} must be a non-empty list of strings.")
        elif not isinstance(value, expected):
            raise RecipeError(f"block {index} ({kind}): {name!r} has the wrong type (got {value!r}).")
        if "range" in pspec:
            low, high = pspec["range"]
            _check_number(value, low, high, f"block {index} ({kind}) {name!r}")
        if pspec.get("values") is not None and value not in pspec["values"]:
            raise RecipeError(
                f"block {index} ({kind}): {name!r} must be one of {list(pspec['values'])}, got {value!r}."
            )
        normalized[name] = value
    if kind == "tte":
        # Fail fast on unknown effects; deep param checking happens at build time
        # where the engine's own parser gives precise errors.
        from .runner import resolve_effect

        try:
            resolve_effect(normalized["effect"])
        except Exception as exc:
            raise RecipeError(f"block {index} (tte): {exc}") from None
    return normalized


def validate_recipe(data: Any) -> dict[str, Any]:
    """Validate a parsed recipe; return normalized copy or raise RecipeError."""
    if not isinstance(data, dict):
        raise RecipeError("recipe must be a JSON object.")
    version = data.get("format_version")
    if version != RECIPE_FORMAT_VERSION:
        raise RecipeError(
            f"unsupported recipe format_version {version!r} (this player supports {RECIPE_FORMAT_VERSION})."
        )
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise RecipeError("recipe needs a non-empty string 'name'.")
    blocks = data.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise RecipeError("recipe needs a non-empty 'blocks' list.")
    extra = set(data) - {"format_version", "name", "description", "seed", "blocks", "layers", "capabilities"}
    if extra:
        raise RecipeError(f"recipe has unknown top-level fields: {sorted(extra)}.")
    layers = data.get("layers", [])
    if not isinstance(layers, list):
        raise RecipeError("'layers' must be a list.")
    if layers:
        raise RecipeError(
            "recipe 'layers' are reserved for a later milestone (per-cell "
            "compositing). Express ambient behavior with 'ambient' blocks today, "
            "which already compose a settled base with shimmer and glitches."
        )
    normalized: dict[str, Any] = {
        "format_version": RECIPE_FORMAT_VERSION,
        "name": name,
        "description": data.get("description", ""),
        "seed": data.get("seed"),
        "capabilities": data.get("capabilities", []),
        "layers": [],
        "blocks": [validate_block(i, b) for i, b in enumerate(blocks)],
    }
    if normalized["seed"] is not None and not isinstance(normalized["seed"], int):
        raise RecipeError("'seed' must be an integer.")
    if not isinstance(normalized["description"], str):
        raise RecipeError("'description' must be a string.")
    if not isinstance(normalized["capabilities"], list):
        raise RecipeError("'capabilities' must be a list.")
    return normalized


def load_recipe(source: str | Path | dict) -> dict[str, Any]:
    """Load + validate a recipe from a path, a JSON string, or a dict."""
    if isinstance(source, dict):
        return validate_recipe(source)
    text: str
    candidate = Path(str(source))
    if candidate.exists() and candidate.is_file():
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError as exc:
            raise RecipeError(f"cannot read recipe file {source}: {exc}") from None
    else:
        # Otherwise the source must be JSON text (arrays included) — a missing
        # path that is not JSON either gets a combined, honest error.
        try:
            return validate_recipe(json.loads(str(source)))
        except json.JSONDecodeError:
            raise RecipeError(
                f"recipe file not found: {source} (and it is not valid JSON either)"
            ) from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RecipeError(f"recipe is not valid JSON: {exc}") from None
    return validate_recipe(data)


def build_effect_config(effect_name: str, params: dict[str, Any]):
    """Build a TTE effect config from recipe params via the engine's own parser.

    Values may be strings (CLI-style) or JSON scalars; argparse applies the
    engine's type parsers. Unknown or invalid params raise RecipeError.
    """
    from .catalog import effect_classes

    mapping = effect_classes()
    if effect_name not in mapping:
        raise RecipeError(f"unknown effect: {effect_name!r}.")
    _, config_cls = mapping[effect_name]
    parser = argparse.ArgumentParser()
    config_cls._populate_parser(parser)
    argv: list[str] = []
    for key, value in params.items():
        flag = key if key.startswith("--") else f"--{key}"
        if isinstance(value, bool):
            if value:
                argv.append(flag)
        elif isinstance(value, (list, tuple)):
            argv.extend([flag, *(str(v) for v in value)])
        else:
            argv.extend([flag, str(value)])
    try:
        ns, extras = parser.parse_known_args(argv)
    except SystemExit as exc:
        raise RecipeError(f"invalid params for effect {effect_name!r}: {params!r}.") from exc
    if extras:
        raise RecipeError(f"unknown params for effect {effect_name!r}: {extras!r}.")
    try:
        return config_cls._build_config(ns)
    except SystemExit as exc:
        raise RecipeError(f"invalid params for effect {effect_name!r}: {params!r}.") from exc


def block_catalogue() -> dict[str, Any]:
    """Machine-readable block catalogue for AI agents (no ANSI, JSON-safe)."""
    from .catalog import discover_effects

    blocks = {}
    for kind, spec in BLOCK_SPECS.items():
        params = {}
        for name, pspec in spec["params"].items():
            entry: dict[str, Any] = {"required": bool(pspec.get("required", False))}
            t = pspec["type"]
            entry["type"] = (
                "number" if t == (int, float) else "integer" if t is int
                else "object" if t is dict else "string-list" if t is list else "string"
            )
            if "default" in pspec and pspec["default"] is not None:
                entry["default"] = pspec["default"]
            if "range" in pspec:
                entry["min"], entry["max"] = pspec["range"]
            if pspec.get("values") is not None:
                entry["values"] = list(pspec["values"])
            params[name] = entry
        blocks[kind] = {"help": spec["help"], "params": params}
    return {
        "recipe_format_version": RECIPE_FORMAT_VERSION,
        "layers_supported": False,  # reserved; ambient blocks cover v1 needs
        "blocks": blocks,
        "tte_effects": [info.name for info in discover_effects()],
    }
