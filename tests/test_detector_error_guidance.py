"""The detector failure envelope must be actionable from an MCP client alone.

Round-2 dogfooding showed agents act on tool errors, not on capability listings, and
that a bare shell command in the message sends them to the wrong environment.
"""

import pytest

from stratigraphic_amenity.map_processing.errors import DetectorLoadError
from stratigraphic_amenity.mcp.adapter import GeomapMcpAdapter
from stratigraphic_amenity.mcp.errors import McpToolError


GATE = "GEOMAP_MCP_ENABLE_DETECTOR_PREPARATION"


class _Registry:
    def map_public(self, map_id):
        return {"map_id": map_id}

    def source_path(self, _map_id):
        return "/redacted/map.png"


class _MissingRuntime:
    def process_image(self, _path):
        raise DetectorLoadError(
            "The managed PEACE YOLOv10 runtime is missing. Run "
            "`stratigraphic-amenity-assets peace-yolov10-runtime`."
        )


def _raise(monkeypatch, tmp_path):
    monkeypatch.setenv("GEOMAP_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", str(tmp_path / "cache"))
    adapter = GeomapMcpAdapter(registry=_Registry(), map_service_factory=_MissingRuntime)
    with pytest.raises(McpToolError) as excinfo:
        adapter.process_image(map_id="map")
    return excinfo.value


def test_detector_error_when_preparation_is_exposed(tmp_path, monkeypatch):
    monkeypatch.delenv(GATE, raising=False)

    error = _raise(monkeypatch, tmp_path)
    hints = " ".join(error.recovery_hints)
    missing = error.details["missing_requirements"]

    assert "geomap_prepare_detectors" in hints
    assert "confirm" in hints.lower()
    assert "shell" in hints.lower()
    assert any("runtime" in item for item in missing)
    assert any("weights" in item for item in missing)
    assert "PEACE YOLOv10 runtime is missing" in error.details["detector_error"]
    assert str(tmp_path) not in str(error.to_dict())
    assert "details.missing_requirements" not in error.message
    for item in error.details["missing_requirements"]:
        assert item in error.message
    assert "geomap_prepare_detectors" in error.message


def test_detector_error_when_preparation_is_withheld(tmp_path, monkeypatch):
    monkeypatch.setenv(GATE, "false")

    error = _raise(monkeypatch, tmp_path)
    hints = " ".join(error.recovery_hints)

    assert "Call `geomap_prepare_detectors`" not in hints
    assert "operator" in hints.lower()
    assert '--root "$GEOMAP_DATA_ROOT"' in hints
    assert "Call `geomap_prepare_detectors`" not in error.message
    assert "operator" in error.message.lower()
