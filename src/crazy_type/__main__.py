"""Allow `python -m crazy_type` as an alias for the crazytype script."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
