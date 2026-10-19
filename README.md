# Crazy Type

Fast, playful terminal-text animations for humans and AI agents.

```sh
crazytype "Hello world"
crazytype "ERROR: failure" --auto
crazytype "Hello" --effect decrypt
crazytype "Hello" --random
crazytype --demo
crazytype effects
```

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
uv tool install git+https://github.com/matthewjameswatkins1978-cyber/crazy-type.git
```

Or from a checkout:

```sh
git clone https://github.com/matthewjameswatkins1978-cyber/crazy-type.git
cd crazy-type
uv sync
uv run crazytype "Hello world"
```

## Usage

| Command | What it does |
|---|---|
| `crazytype "Some text"` | Animate with the default effect (`decrypt`) |
| `crazytype "ERROR: x" --auto` | Auto Director picks an effect for your text (error, warning, success, startup, ordinary) |
| `crazytype "Hi" --effect matrix` | Use an explicit effect |
| `crazytype "Hi" --random [--seed 7]` | Random effect; `--seed` replays it exactly |
| `crazytype "Hi" --calm` / `--chaos` | Gentle / wild preset pools |
| `crazytype "Hi" --figlet [FONT]` | ASCII-art banner first, then animate |
| `crazytype "Hi" --plain` | No animation, just print |
| `echo hi \| crazytype --effect waves` | Piped input works |
| `crazytype --demo` | Interactive showcase of 12 effects |
| `crazytype effects [--json]` | List all effects, human or machine readable |
| `crazytype doctor [--json]` | Environment diagnostics |
| `crazytype --version` | Version |
| `crazytype studio [recipe]` | Keyboard-first visual editor: remix blocks, preview, save |
| `crazytype studio --demo [recipe]` | Play the recipe once, then open the editor ready to remix |
| `crazytype play <recipe> [text]` | Play a recipe file (bundled names work too) |
| `crazytype blocks [--json]` | Recipe block catalogue for humans and AI agents |
| `crazytype export <recipe> [text] --recipe/--cast` | Export validated recipe / asciicast recording |

Exit codes: `0` success · `1` runtime error / empty input · `2` usage error · `130` interrupted (Ctrl+C).

Animation is automatically skipped (plain text printed) when output is
redirected, running in CI, `TERM=dumb`, `NO_COLOR` is set, a reduced-motion
preference is set, the console encoding cannot render animation glyphs
(Windows Terminal is UTF-8 by default; otherwise `chcp 65001`), or `--plain`
/ `CRAZYTYPE_PLAIN=1` is used. No AI service,
model call, server or account is ever required.

Some upstream effects are long-form by design (notably `matrix`, which can
run for many minutes) — the `--demo` showcase sticks to snappy ones so it
finishes in about a minute.

## Recipes, Studio and embedding

A Recipe (versioned JSON) describes an effect independently of any editor:
`crazytype play giant-growth "Hello"` plays a bundled recipe; any `.json`
recipe file works too. `crazytype blocks --json` is the machine-readable block
catalogue AI agents build recipes from. `crazytype studio [recipe]` opens the
keyboard-first editor (pick a block, tweak a value, `p` to preview with the
exact runtime the CLI uses, `s` to save). `crazytype export` writes a
validated recipe envelope or an asciicast v2 recording (with its recorded
terminal size) for sharing and embedding. Embed via CLI subprocess, the
`crazy_type.runtime.play_recipe` API, or a recording — see `docs/DECISIONS.md`.

## Watch it work

[`docs/demo/studio-remix.cast`](docs/demo/studio-remix.cast) is a real
10-second Studio session recorded from the actual renderer: open a recipe,
move, duplicate a block (remix), preview it with real animation, undo, and
quit through the unsaved-work guard. Replay it with any asciicast player:

```sh
npx asciinema play docs/demo/studio-remix.cast
```

Regenerate it deterministically with `uv run python tools/record_demo.py`.

## Testing

`uv run pytest -q` runs the full suite (also on Ubuntu + Windows via CI).
`uv run python tools/conpty_dogfood.py` drives the real CLI under a genuine
Windows pseudo-terminal: true-console playback, real Ctrl+C, real Studio
keys. It asserts mechanics (exits, cursor restoration, saved files) — visual
quality still needs human eyes.

## Credits

Crazy Type is a thin, friendly shell around excellent upstream work — it
contains no copied animation engine code:

- [terminaltexteffects](https://github.com/ChrisBuilds/terminaltexteffects) by ChrisBuilds (MIT) — the animation engine
- [pyfiglet](https://github.com/pwaller/pyfiglet) by Peter Waller and contributors (BSD-2-Clause) — optional ASCII-art banners

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Crazy Type itself is MIT — see [LICENSE](LICENSE).

## Versioning

Follows Matthew's rule: `v0.<feature>.<fix>` while pre-1.0, patch bumps for
fixes, minor bumps for features. Latest release is **v0.1.1**; the recipe
runtime, Studio and export work in this branch is unreleased (no tag, no
merge) until reviewed.
