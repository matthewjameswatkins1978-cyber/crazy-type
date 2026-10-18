# Crazy Type Architecture Decisions

## ADR-1 (2026-10-17): Composition over rewrite — Python runtime over TTE

**Decision:** Build the next-generation system as a Python composition layer over
TerminalTextEffects. No Rust/Ratatui migration.

**Evidence:**
- TTE ships 37 working effects with typed, bounded, defaulted configs
  (`DecryptConfig`: `typing_speed`, `ciphertext_colors`, gradient stops/steps/…).
- Recipe-style `{effect, params}` maps onto real configs via the engine's own
  `_populate_parser` + `_build_config` path: defaults resolve (`typing_speed=2`),
  overrides type-parse (`"5"`→`5`, `["ff0000"]`→`(Color('ff0000'),)`), unknown
  params and unknown effects fail loudly (probes on `feature/nextgen-studio`).
- Sequencing works with stock TTE contexts. Boundary-byte probes show two modes:
  default stacks the next block below the previous final frame; `--reuse-canvas`
  reuses the same screen region in place.
- `crumble` ("crumble into dust… vacuumed up and reformed") already covers the
  explode→reassemble loop needed for Particle Reconstruction.
- Rust candidates are healthy (crates.io: ratatui 0.30.2, 61M downloads;
  tachyonfx 0.25.2, both updated mid/late-2026) — but a rewrite would discard a
  working, tested product to solve no demonstrated Python-side blocker.
- Known upstream quirk, not a blocker: `matrix` with defaults runs ~400k frames
  (random rain tail). Handled by curation (kept out of the demo), not forking.

**Consequences:** TTE stays the animation engine. New code owns exactly one
canonical frame pipeline (cursor save/draw/restore, pacing, cancellation,
cleanup) plus custom generator blocks (wait/hold, ambient shimmer/glitch,
figlet growth stages). Preview and playback share that pipeline.

## ADR-2 (2026-10-17): Recipes are versioned JSON, validated before play

**Decision:** `{format_version, name, blocks[], layers[], timing, seed,
capabilities}`. Declarative data only — never executable code. Text supplied at
playback. AI and Studio read/write the same schema; no parallel systems.

## ADR-3 (2026-10-17): Layers v1 = ambient-over-base, not frame merging

**Decision:** TTE frames are opaque full-canvas strings with no cell-level merge
API, so v1 layers compose inside our pipeline (e.g. shimmer recolor passes over
a settled base) rather than by merging two TTE streams. Full per-cell layering
is deferred until evidence demands it.

## ADR-4 (2026-10-17): Studio in Python, player stays light

**Decision:** The Studio editor will be a Python terminal UI (library TBD at
Studio milestone; textual is the leading candidate). The Player/Runtime stays
TTE + stdlib so embedding never drags in editor frameworks. v0.1.1 CLI behaviour
and its 41 tests remain the untouched baseline throughout.

## ADR-5 (2026-10-17): Studio v1 is stdlib-only, preview shares the runtime

**Decision:** `crazy_type/studio.py` uses only the standard library
(alt-screen + `msvcrt`/`termios` keys) so the whole project stays
dependency-light. The editor mutates the same validated recipe model the CLI
plays, and preview calls `runtime.play_recipe` directly — preview and playback
cannot drift. Undo/redo are validated snapshots; all exit paths restore the
terminal. Known limitation: preview temporarily takes over the screen rather
than playing in a bounded region; bounded-region preview is a later milestone.

## ADR-6 (2026-10-17): Export = recipe envelope + asciicast recording

**Decision:** Two honest formats. Editable Recipe: the validated `.json`
(openable by any Crazy Type install). ANSI Recording: asciicast v2 captured
from a real paced playback, stamped with its terminal size, cursor restore
included. No standalone-binary or TTE-free export is promised: TTE effects
need their runtime, and the recording header says so by construction.

## ADR-7 (2026-10-17): Console-portable output — CRLF + ASCII chrome

**Decision:** All first-party screen writes use CRLF (bare LF staggers the
column on real VT consoles) and Studio chrome is ASCII-only, so the editor
survives non-UTF-8 consoles (proven under a default-codepage ConPTY, where
box-drawing crashed before the fix). Animation *content* (TTE glyphs, FIGlet)
keeps requiring UTF-8 — documented, not disguised. Mechanical dogfooding
(real ConPTY: playback, Ctrl+C→130, Studio keys, cursor restore) is recorded
here; visual aesthetics still need human eyes.

## Appendix (2026-10-18): runtime size and performance observations

- Crazy Type's own code: ~185 KB source (runtime, recipes, Studio, export).
  Zero new dependencies on the feature branch — Studio is stdlib-only, so the
  player stays TTE + pyfiglet + stdlib.
- Installed footprint is dominated by upstream: terminaltexteffects ~2.0 MB,
  pyfiglet ~6.9 MB (mostly bundled FIGlet fonts). Built wheel: ~12 KB.
- Startup: `crazytype --version` in ~0.34 s (uv overhead included),
  `import crazy_type.cli` in ~0.17 s. No lazy-import debt.
- Ambient (living-neon) pacing: frames cost ~8 us each to compute
  (~131k frames/s achievable) against a 10 fps cap — continuous animation
  sips CPU by design; one-shot CLI effects keep full 60 fps pacing.
- Playback memory is flat: frames stream to the terminal, nothing
  accumulates.
