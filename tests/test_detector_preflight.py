import sys

from stratigraphic_amenity.map_processing.detectors.preflight import detector_preflight


def test_preflight_reports_native_import_failure_from_subprocess(tmp_path, monkeypatch):
    modules = tmp_path / "modules"
    modules.mkdir()
    (modules / "cv2.py").write_text(
        "raise ImportError('libGL.so.1: cannot open shared object file')\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", str(modules))

    failures = detector_preflight(tmp_path / "missing-runtime")

    assert any("libGL.so.1" in failure for failure in failures)
    assert "cv2" not in sys.modules
