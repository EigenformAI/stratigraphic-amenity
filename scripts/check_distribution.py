#!/usr/bin/env python3
"""Compare built distribution contents with checked-in release allowlists."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    args = parser.parse_args()
    wheels = list(args.dist.glob("*.whl"))
    sdists = list(args.dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit("expected exactly one wheel and one .tar.gz sdist")

    with zipfile.ZipFile(wheels[0]) as archive:
        wheel_files = {name for name in archive.namelist() if not name.endswith("/")}
    with tarfile.open(sdists[0], "r:gz") as archive:
        sdist_files = {
            member.name.split("/", 1)[1]
            for member in archive.getmembers()
            if member.isfile() and "/" in member.name
        }

    _compare("wheel", wheel_files, _allowlist("wheel-files.txt"))
    _compare("sdist", sdist_files, _allowlist("sdist-files.txt"))
    print(f"approved wheel files: {len(wheel_files)}")
    print(f"approved sdist files: {len(sdist_files)}")
    return 0


def _allowlist(name: str) -> set[str]:
    return {
        line
        for line in (ROOT / "release" / name).read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }


def _compare(label: str, actual: set[str], expected: set[str]) -> None:
    added = sorted(actual - expected)
    missing = sorted(expected - actual)
    if added or missing:
        details = [f"{label} contents differ from release allowlist"]
        details.extend(f"unexpected: {name}" for name in added)
        details.extend(f"missing: {name}" for name in missing)
        raise SystemExit("\n".join(details))


if __name__ == "__main__":
    raise SystemExit(main())
