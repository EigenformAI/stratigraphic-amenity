"""Stable default state paths for installed and source-checkout use."""

from __future__ import annotations

import os
from pathlib import Path


APP_SLUG = "stratigraphic-amenity"


def default_data_root() -> Path:
    base = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return (base / APP_SLUG).expanduser().resolve()


def default_cache_root() -> Path:
    base = Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache"))
    return (base / APP_SLUG).expanduser().resolve()


def path_base(base_dir: str | Path | None) -> Path:
    """Resolve explicit relative environment values against the launch directory."""

    return Path(base_dir).resolve() if base_dir is not None else Path.cwd().resolve()


__all__ = ["APP_SLUG", "default_cache_root", "default_data_root", "path_base"]
