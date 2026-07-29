import sys
import types

import pytest

from stratigraphic_amenity.map_processing.detectors.preflight import detector_preflight


@pytest.mark.parametrize("cv2_already_imported", [False, True])
def test_preflight_reports_native_import_failure_from_subprocess(
    tmp_path, monkeypatch, cv2_already_imported
):
    if cv2_already_imported:
        monkeypatch.setitem(sys.modules, "cv2", types.ModuleType("cv2"))
    modules = tmp_path / "modules"
    modules.mkdir()
    (modules / "cv2.py").write_text(
        "raise ImportError('libGL.so.1: cannot open shared object file')\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", str(modules))

    imported_before = "cv2" in sys.modules
    failures = detector_preflight(tmp_path / "missing-runtime")

    assert any("libGL.so.1" in failure for failure in failures)
    # The probe runs in a subprocess so the caller never imports the heavy
    # dependencies. Assert the delta: `sys.modules` is process-global, and
    # asserting cv2's absence outright makes this test fail whenever an earlier
    # test in the same session imported it.
    assert ("cv2" in sys.modules) is imported_before
