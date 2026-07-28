from pathlib import Path

import pytest

from stratigraphic_amenity.asset_installer import InstallResult
from stratigraphic_amenity.map_processing.config import MapProcessingConfig
from stratigraphic_amenity.mcp import adapter as adapter_module
from stratigraphic_amenity.mcp.errors import McpToolError
from stratigraphic_amenity.map_processing.preparation import (
    DETECTOR_ASSET_IDS,
    DetectorPreparationError,
    prepare_detectors,
)


def _config(tmp_path: Path) -> MapProcessingConfig:
    data_root = tmp_path / "data"
    return MapProcessingConfig(
        data_root=data_root,
        model_root=data_root / "assets" / "models",
        cache_root=tmp_path / "cache",
    )


def test_prepare_detectors_installs_only_fixed_manifest_assets(tmp_path):
    calls = []

    def provision(asset_ids, *, root, force=False):
        calls.append((tuple(asset_ids), root, force))
        return [
            InstallResult(asset_id, "installed", Path(root) / asset_id)
            for asset_id in asset_ids
        ]

    result = prepare_detectors(_config(tmp_path), provision=provision)

    assert calls == [(DETECTOR_ASSET_IDS, tmp_path / "data", False)]
    assert result.assets == (
        {"asset_id": "peace-yolov10-runtime", "status": "installed"},
        {"asset_id": "peace-layout-detectors", "status": "installed"},
    )


def test_prepare_detectors_rejects_custom_detector_roots(tmp_path):
    config = _config(tmp_path)
    config.ultralytics_root = tmp_path / "custom-runtime"

    with pytest.raises(DetectorPreparationError, match="manifest destinations"):
        prepare_detectors(config, provision=lambda *_args, **_kwargs: [])


def _stub_preparation(monkeypatch):
    from stratigraphic_amenity.map_processing.preparation import DetectorPreparationResult

    monkeypatch.setattr(
        adapter_module,
        "prepare_detectors",
        lambda _config: DetectorPreparationResult(
            assets=({"asset_id": "peace-yolov10-runtime", "status": "installed"},)
        ),
    )


def test_adapter_prepare_detectors_runs_without_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv("GEOMAP_MCP_ENABLE_DETECTOR_PREPARATION", raising=False)
    monkeypatch.setenv("GEOMAP_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", str(tmp_path / "cache"))
    _stub_preparation(monkeypatch)

    result = adapter_module.GeomapMcpAdapter().prepare_detectors()

    assert result["structuredContent"]["assets"]


def test_adapter_prepare_detectors_summary_reflects_readiness(tmp_path, monkeypatch):
    """Assets alone cannot make the detector ready; the summary must not imply they do."""

    monkeypatch.delenv("GEOMAP_MCP_ENABLE_DETECTOR_PREPARATION", raising=False)
    monkeypatch.setenv("GEOMAP_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", str(tmp_path / "cache"))
    _stub_preparation(monkeypatch)

    result = adapter_module.GeomapMcpAdapter().prepare_detectors()

    assert result["structuredContent"]["map_processing"]["ready"] is False
    assert "not ready" in result["structuredContent"]["text_summary"].lower()
    assert result["structuredContent"]["warnings"]


def test_adapter_prepare_detectors_refuses_when_opted_out(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOMAP_MCP_ENABLE_DETECTOR_PREPARATION", "false")
    monkeypatch.setenv("GEOMAP_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", str(tmp_path / "cache"))
    _stub_preparation(monkeypatch)

    with pytest.raises(McpToolError) as excinfo:
        adapter_module.GeomapMcpAdapter().prepare_detectors()

    assert excinfo.value.code == "preparation_disabled"
