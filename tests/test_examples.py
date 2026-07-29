import base64
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGA"
    "WjR9awAAAABJRU5ErkJggg=="
)


@pytest.mark.parametrize("script", ["01_process_map.py"])
def test_examples_have_portable_help(script):
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples" / script), "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def test_georeference_example_runs_with_explicit_inputs(tmp_path):
    pytest.importorskip("pyproj")
    image = tmp_path / "map.png"
    image.write_bytes(PNG_1X1)

    result = _run_spatial_example("02_georeference_map.py", image)

    assert result.returncode == 0, result.stderr
    assert "bounds (EPSG:4326)" in result.stdout


def test_overlay_example_runs_offline_with_recorded_bundle(tmp_path):
    pytest.importorskip("cv2")
    pytest.importorskip("pyproj")
    image = tmp_path / "map.png"
    output = tmp_path / "overlay.png"
    bundle = tmp_path / "bundle.json"
    image.write_bytes(PNG_1X1)
    bundle.write_text(
        json.dumps(
            {
                "schema_version": "knowledge/v2",
                "bounds": {"min_lon": -90, "min_lat": 45, "max_lon": -89, "max_lat": 46},
                "items": [],
                "selected_item_ids": None,
                "warnings": [],
                "provider_versions": {},
                "trace": None,
            }
        ),
        encoding="utf-8",
    )

    result = _run_spatial_example(
        "03_knowledge_overlay_on_map.py",
        image,
        "--bundle",
        str(bundle),
        "--out",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    assert output.exists()


def _run_spatial_example(script, image, *extra):
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples" / script),
            str(image),
            *extra,
            "--crs",
            "EPSG:4326",
            "--gcp",
            "0",
            "0",
            "-90",
            "46",
            "--gcp",
            "1",
            "1",
            "-89",
            "45",
            "--pixel-extent",
            "0",
            "0",
            "1",
            "1",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
