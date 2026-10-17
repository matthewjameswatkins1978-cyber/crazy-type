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

Exit codes: `0` success · `1` runtime error / empty input · `2` usage error · `130` interrupted (Ctrl+C).

Animation is automatically skipped (plain text printed) when output is
redirected, running in CI, `TERM=dumb`, `NO_COLOR` is set, a reduced-motion
preference is set, or `--plain` / `CRAZYTYPE_PLAIN=1` is used. No AI service,
model call, server or account is ever required.

Some upstream effects are long-form by design (notably `matrix`, which can
run for many minutes) — the `--demo` showcase sticks to snappy ones so it
finishes in about a minute.

## Credits

Crazy Type is a thin, friendly shell around excellent upstream work — it
contains no copied animation engine code:

- [terminaltexteffects](https://github.com/ChrisBuilds/terminaltexteffects) by ChrisBuilds (MIT) — the animation engine
- [pyfiglet](https://github.com/pwaller/pyfiglet) by Peter Waller and contributors (BSD-2-Clause) — optional ASCII-art banners

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Crazy Type itself is MIT — see [LICENSE](LICENSE).

## Versioning

Follows Matthew's rule: `v0.<feature>.<fix>` while pre-1.0, patch bumps for
fixes, minor bumps for features. This release is **v0.1.0**.
