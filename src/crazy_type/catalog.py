"""Effect catalogue: discover the animation effects shipped by terminaltexteffects.

We reuse the installed TTE engine as-is — no animation code is copied here.
This module only discovers effect names, classes and help text so Crazy Type
can expose one clean, discoverable catalogue over them.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from functools import lru_cache

import terminaltexteffects.effects


@dataclass(frozen=True)
class EffectInfo:
    """One entry in the Crazy Type effect catalogue."""

    name: str
    title: str
    help: str


def _iter_effect_modules():
    for module_info in pkgutil.iter_modules(
        terminaltexteffects.effects.__path__,
        terminaltexteffects.effects.__name__ + ".",
    ):
        module = importlib.import_module(module_info.name)
        if hasattr(module, "get_effect_resources"):
            yield module


@lru_cache(maxsize=1)
def discover_effects() -> tuple[EffectInfo, ...]:
    """Return every compatible TTE effect, sorted by name. Cached per process."""
    found: dict[str, EffectInfo] = {}
    for module in _iter_effect_modules():
        command, effect_class, config_class = module.get_effect_resources()
        help_text = ""
        try:
            spec = getattr(config_class, "parser_spec", None)
            default = getattr(spec, "default", spec)
            help_text = getattr(default, "help", "") or ""
        except Exception:  # noqa: BLE001 - catalogue must never crash on one bad effect
            help_text = ""
        if command not in found:
            found[command] = EffectInfo(
                name=command,
                title=effect_class.__name__,
                help=str(help_text),
            )
    return tuple(sorted(found.values(), key=lambda info: info.name))


def effect_names() -> list[str]:
    """Sorted list of available effect names."""
    return [info.name for info in discover_effects()]


def get_effect_info(name: str) -> EffectInfo | None:
    """Look up one effect by exact name, or None."""
    for info in discover_effects():
        if info.name == name:
            return info
    return None


def effect_classes() -> dict[str, tuple[type, type]]:
    """Map effect name -> (effect class, config class) for the animation runner."""
    mapping: dict[str, tuple[type, type]] = {}
    for module in _iter_effect_modules():
        command, effect_class, config_class = module.get_effect_resources()
        mapping.setdefault(command, (effect_class, config_class))
    return mapping
