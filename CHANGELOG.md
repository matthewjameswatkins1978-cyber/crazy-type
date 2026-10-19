# Changelog

All notable changes to Crazy Type. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow the
project's patch/minor rule (pre-1.0: `0.<feature>.<patch>`).

## [Unreleased] — on `feature/nextgen-studio` (not yet merged or tagged)

### Added
- **Recipe runtime (format v1):** versioned, validated JSON recipes with four
  block kinds — `tte` (wraps all 37 installed effects), `hold`, `ambient`
  (living text: shimmer + seeded glitches, duration-bounded), `grow`
  (FIGlet growth/shrink). Sequence blocks stacked or in-place.
- **Three bundled recipes:** `giant-growth`, `living-neon`,
  `particle-reconstruction`, playable via `crazytype play <name> "<text>"`.
- **Crazy Type Studio:** keyboard-first terminal editor
  (`crazytype studio [recipe]`) — add/remove/reorder/duplicate blocks,
  guided parameter prompts, searchable effect picker, undo/redo, save/open,
  in-loop preview using the exact runtime the CLI plays.
- **Export:** `crazytype export <recipe> --recipe out.json` (validated
  envelope) and `--cast out.cast` (asciicast v2 with terminal size stamped).
- **Discovery:** `crazytype blocks [--json]` machine-readable block catalogue.
- **CI:** GitHub Actions on Ubuntu + Windows.
- **Testing:** `tools/conpty_dogfood.py` drives the real CLI under a genuine
  Windows pseudo-terminal (mechanics, not aesthetics).

### Fixed
- Console encoding without glyph support (e.g. cp1252) now falls back to
  plain text with a hint instead of crashing mid-animation.
- All first-party screen output uses CRLF; Studio chrome is ASCII-only, so
  both survive non-UTF-8 consoles (ADR-7).
- Studio navigation: `q`/`esc` back out of every sub-screen; unsaved-quit is
  armed with explicit status instead of a confusing typed prompt.
- Studio text prompts read the key channel instead of stdin (some consoles
  report instant-EOF on fd 0, which silently ate input).
- Bundled recipe names are never treated as save destinations; shipped
  recipe files can no longer be overwritten from Studio.
- Stale parameter selection between blocks clamps instead of crashing.

### Compatibility
- v0.1.1 behaviour preserved: all original commands, effects and tests
  unchanged (41 baseline tests still green).

## [0.1.1] — 2026-10-17

### Fixed
- Demo shows a visible prompt at each step (`[Enter]=next effect, q=quit`).

## [0.1.0] — 2026-10-17

### Added
- Initial release: `crazytype` CLI over the TerminalTextEffects engine —
  37-effect catalogue, Auto Director (`--auto`), `--random/--calm/--chaos`
  presets with seeded replay, `--figlet` banners, interactive `--demo`,
  `effects/doctor [--json]` machine discovery, plain-text fallbacks
  (redirect/CI/NO_COLOR/reduced motion), cursor restore on exit and Ctrl+C.
