from types import SimpleNamespace

from stratigraphic_amenity.mcp.adapter import GeomapMcpAdapter
from stratigraphic_amenity.mcp.resources import ResourceRegistry


def test_capabilities_separate_registration_from_readiness(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    cache_root = tmp_path / "cache"
    model_root = tmp_path / "models"
    data_root.mkdir()
    cache_root.mkdir()
    model_root.mkdir()
    monkeypatch.setenv("GEOMAP_DATA_ROOT", str(data_root))
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", str(cache_root))
    monkeypatch.setenv("GEOMAP_MODEL_ROOT", str(model_root))
    monkeypatch.setenv("GEOMAP_MCP_ALLOWED_ROOTS", f"{data_root}:{cache_root}")
    service = SimpleNamespace(
        _registrations=[
            SimpleNamespace(
                id="fixture_provider",
                name="Fixture provider",
                output_keys=("fixture",),
                default_enabled=True,
            )
        ]
    )
    adapter = GeomapMcpAdapter(
        registry=ResourceRegistry.from_env(base_dir=tmp_path),
        knowledge_service_factory=lambda: service,
    )

    result = adapter.list_capabilities()["structuredContent"]

    assert set(result["capabilities"]) >= {
        "map_registration",
        "map_processing",
        "georeferencing",
        "knowledge_query",
        "overlay_rendering",
    }
    for capability in result["capabilities"].values():
        assert set(capability) >= {
            "registered",
            "installed",
            "configured",
            "ready",
            "missing_requirements",
        }
    assert result["capabilities"]["map_processing"]["registered"] is True
    assert result["capabilities"]["map_processing"]["ready"] is False
    assert result["capabilities"]["map_processing"]["missing_requirements"]
    assert result["providers"][0]["registered"] is True
    assert "ready" in result["providers"][0]


def test_unrelated_ultralytics_install_cannot_replace_managed_runtime(tmp_path, monkeypatch):
    from stratigraphic_amenity.mcp import adapter as adapter_module

    data_root = tmp_path / "data"
    cache_root = tmp_path / "cache"
    model_root = tmp_path / "models"
    for path in (
        data_root,
        cache_root,
        model_root / "det_component" / "weights",
        model_root / "det_legend" / "weights",
    ):
        path.mkdir(parents=True)
    (model_root / "det_component" / "weights" / "best.pt").write_bytes(b"private")
    (model_root / "det_legend" / "weights" / "best.pt").write_bytes(b"private")
    monkeypatch.setenv("GEOMAP_DATA_ROOT", str(data_root))
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", str(cache_root))
    monkeypatch.setenv("GEOMAP_MODEL_ROOT", str(model_root))
    monkeypatch.setenv("GEOMAP_MCP_ALLOWED_ROOTS", f"{data_root}:{cache_root}")
    monkeypatch.setattr(adapter_module, "_module_available", lambda _name: True)
    service = SimpleNamespace(_registrations=[])
    adapter = GeomapMcpAdapter(
        registry=ResourceRegistry.from_env(base_dir=tmp_path),
        knowledge_service_factory=lambda: service,
    )

    status = adapter.list_capabilities()["structuredContent"]["capabilities"]["map_processing"]

    assert status["installed"] is False
    assert status["ready"] is False
    assert any("managed PEACE YOLOv10 runtime" in requirement for requirement in status["missing_requirements"])


def test_managed_runtime_and_weights_make_map_processing_ready(tmp_path, monkeypatch):
    from stratigraphic_amenity.mcp import adapter as adapter_module

    data_root = tmp_path / "data"
    cache_root = tmp_path / "cache"
    model_root = data_root / "assets" / "models"
    runtime_root = data_root / "assets" / "runtime" / "ultralytics"
    for path in (
        cache_root,
        model_root / "det_component" / "weights",
        model_root / "det_legend" / "weights",
        runtime_root / "models" / "yolov10",
    ):
        path.mkdir(parents=True)
    (model_root / "det_component" / "weights" / "best.pt").write_bytes(b"component")
    (model_root / "det_legend" / "weights" / "best.pt").write_bytes(b"legend")
    (runtime_root / "__init__.py").write_text("class YOLOv10: pass\n", encoding="utf-8")
    (runtime_root / "models" / "yolov10" / "model.py").write_text("", encoding="utf-8")
    monkeypatch.setenv("GEOMAP_DATA_ROOT", str(data_root))
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", str(cache_root))
    monkeypatch.setenv("GEOMAP_MODEL_ROOT", str(model_root))
    monkeypatch.setenv("GEOMAP_ULTRALYTICS_ROOT", str(runtime_root))
    monkeypatch.setenv("GEOMAP_MCP_ALLOWED_ROOTS", f"{data_root}:{cache_root}")
    monkeypatch.setattr(adapter_module, "_module_available", lambda _name: True)
    service = SimpleNamespace(_registrations=[])
    adapter = GeomapMcpAdapter(
        registry=ResourceRegistry.from_env(base_dir=tmp_path),
        knowledge_service_factory=lambda: service,
    )

    status = adapter.list_capabilities()["structuredContent"]["capabilities"]["map_processing"]

    assert status["installed"] is True
    assert status["configured"] is True
    assert status["ready"] is True
    assert status["missing_requirements"] == []
