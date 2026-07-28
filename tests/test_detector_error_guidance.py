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


def test_error_recommends_the_preparation_tool_when_exposed(tmp_path, monkeypatch):
    monkeypatch.delenv(GATE, raising=False)

    error = _raise(monkeypatch, tmp_path)
    hints = " ".join(error.recovery_hints)

    assert "geomap_prepare_detectors" in hints
    assert "confirm" in hints.lower()


def test_error_escalates_to_the_operator_when_withheld(tmp_path, monkeypatch):
    monkeypatch.setenv(GATE, "false")

    error = _raise(monkeypatch, tmp_path)
    hints = " ".join(error.recovery_hints)

    assert "Call `geomap_prepare_detectors`" not in hints
    assert "operator" in hints.lower()
    assert '--root "$GEOMAP_DATA_ROOT"' in hints


def test_error_always_warns_against_the_client_shell(tmp_path, monkeypatch):
    monkeypatch.delenv(GATE, raising=False)

    hints = " ".join(_raise(monkeypatch, tmp_path).recovery_hints)

    assert "shell" in hints.lower()


def test_error_lists_every_missing_requirement_up_front(tmp_path, monkeypatch):
    """Round 2 run A needed seven round-trips partly because each error named one gap."""

    monkeypatch.delenv(GATE, raising=False)

    error = _raise(monkeypatch, tmp_path)
    missing = error.details["missing_requirements"]

    assert any("runtime" in item for item in missing)
    assert any("weights" in item for item in missing)


def test_error_does_not_leak_the_resolved_data_root(tmp_path, monkeypatch):
    monkeypatch.delenv(GATE, raising=False)

    error = _raise(monkeypatch, tmp_path)

    assert str(tmp_path) not in str(error.to_dict())


def test_message_inlines_the_requirements_for_text_only_clients(tmp_path, monkeypatch):
    """A host may surface only `message`; a pointer to details.* reaches nobody."""

    monkeypatch.delenv(GATE, raising=False)

    error = _raise(monkeypatch, tmp_path)

    assert "details.missing_requirements" not in error.message
    for item in error.details["missing_requirements"]:
        assert item in error.message


def test_message_names_the_remedy_not_only_the_hints(tmp_path, monkeypatch):
    """recovery_hints share `message`'s fate: a text-only host shows neither field."""

    monkeypatch.delenv(GATE, raising=False)
    assert "geomap_prepare_detectors" in _raise(monkeypatch, tmp_path).message

    monkeypatch.setenv(GATE, "false")
    withheld = _raise(monkeypatch, tmp_path).message
    assert "Call `geomap_prepare_detectors`" not in withheld
    assert "operator" in withheld.lower()


def test_original_detector_message_is_preserved_in_details(tmp_path, monkeypatch):
    monkeypatch.delenv(GATE, raising=False)

    error = _raise(monkeypatch, tmp_path)

    assert "PEACE YOLOv10 runtime is missing" in error.details["detector_error"]
