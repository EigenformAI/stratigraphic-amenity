"""Side-effect-isolated detector import readiness probe."""

from __future__ import annotations

import importlib
import json
from contextlib import redirect_stdout
from pathlib import Path
import re
import subprocess
import sys
import time


DEPENDENCIES = ("cv2", "cpuinfo", "matplotlib", "numpy", "torch", "yaml")
_CACHE_SECONDS = 10.0
_CACHE: dict[tuple[str, int, int], tuple[float, tuple[str, ...]]] = {}


def detector_preflight(runtime_root: Path) -> tuple[str, ...]:
    """Return sanitized import failures from a fresh Python process."""

    root = runtime_root.expanduser().resolve()
    init_path = root / "__init__.py"
    stat = init_path.stat() if init_path.is_file() else None
    key = (str(root), stat.st_mtime_ns if stat else 0, stat.st_size if stat else 0)
    cached = _CACHE.get(key)
    if cached is not None and cached[0] > time.monotonic():
        return cached[1]
    try:
        completed = subprocess.run(
            [sys.executable, "-m", __name__, str(root)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ("detector import preflight timed out",)
    try:
        failures = tuple(json.loads(completed.stdout))
    except (json.JSONDecodeError, TypeError):
        failures = ("detector import preflight failed",)
    _CACHE[key] = (time.monotonic() + _CACHE_SECONDS, failures)
    return failures


def _probe(runtime_root: Path) -> list[str]:
    failures = []
    for name in DEPENDENCIES:
        try:
            with redirect_stdout(sys.stderr):
                importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - readiness includes native import failures.
            failures.append(_sanitize_import_failure(name, exc))
    if failures:
        return failures
    if not (runtime_root / "__init__.py").is_file():
        return failures
    try:
        from .peace_yolov10 import _load_yolov10_class

        _load_yolov10_class(runtime_root)
    except Exception as exc:  # noqa: BLE001 - report a sanitized transitive cause.
        cause = exc
        while cause.__cause__ is not None:
            cause = cause.__cause__
        failures.append(_sanitize_import_failure("managed PEACE runtime", cause))
    return failures


def _sanitize_import_failure(name: str, exc: BaseException) -> str:
    if isinstance(exc, ModuleNotFoundError) and exc.name:
        return f"{exc.name} is missing"
    match = re.search(r"([A-Za-z0-9_.+-]+\.so(?:\.\d+)*)", str(exc))
    if match:
        return f"{name} import failed: missing shared library {match.group(1)}"
    return f"{name} import failed ({type(exc).__name__})"


def main() -> int:
    failures = _probe(Path(sys.argv[1]))
    print(json.dumps(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["detector_preflight"]
