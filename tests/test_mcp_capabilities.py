from types import SimpleNamespace

from stratigraphic_amenity.mcp.adapter import GeomapMcpAdapter
from stratigraphic_amenity.mcp.resources import ResourceRegistry


def test_capabilities_separate_registration_from_readiness(tmp_path, monkeypatch):
    from stratigraphic_amenity.knowledge import KnowledgeConfig, KnowledgeService

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
                supported_requests=("bounds",),
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
    assert result["providers"][0]["supported_requests"] == ["bounds"]
    assert result["capabilities"]["knowledge_query"]["ready_provider_count"] == 1
    assert result["capabilities"]["knowledge_query"]["registered_provider_count"] == 1

    default_service = KnowledgeService(
        config=KnowledgeConfig(
            data_root=data_root,
            knowledge_root=data_root / "knowledge",
            cache_root=cache_root,
        )
    )
    default_adapter = GeomapMcpAdapter(
        registry=ResourceRegistry.from_env(base_dir=tmp_path),
        knowledge_service_factory=lambda: default_service,
    )
    supported_requests = {
        provider["id"]: provider["supported_requests"]
        for provider in default_adapter.list_capabilities()["structuredContent"]["providers"]
    }

    assert supported_requests == {
        "rock_type": ["legend_labels"],
        "rock_age": ["legend_labels"],
        "earthquake_history": ["bounds"],
        "active_faults": ["bounds"],
        "mineral_occurrences": ["bounds"],
        "landcover_distribution": ["bounds"],
        "population_density": ["bounds"],
        "rock_knowledge": ["query_text"],
        "component_usage_knowledge": ["query_text"],
        "downstream_task_knowledge": ["query_text"],
    }


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
    monkeypatch.setattr(adapter_module, "detector_preflight", lambda _root: ())
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


def test_capabilities_report_import_failure_and_root_aware_commands(tmp_path, monkeypatch):
    from stratigraphic_amenity.mcp import adapter as adapter_module

    data_root = tmp_path / "server-data"
    cache_root = tmp_path / "cache"
    data_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setenv("GEOMAP_DATA_ROOT", str(data_root))
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", str(cache_root))
    monkeypatch.setenv("GEOMAP_MCP_ALLOWED_ROOTS", f"{data_root}:{cache_root}")
    monkeypatch.setattr(
        adapter_module,
        "detector_preflight",
        lambda _root: ("cv2 import failed: missing shared library libGL.so.1", "cpuinfo is missing"),
    )
    adapter = GeomapMcpAdapter(
        registry=ResourceRegistry.from_env(base_dir=tmp_path),
        knowledge_service_factory=lambda: SimpleNamespace(_registrations=[]),
    )

    result = adapter.list_capabilities()["structuredContent"]
    status = result["capabilities"]["map_processing"]

    assert status["ready"] is False
    assert any("libGL.so.1" in item for item in status["missing_requirements"])
    assert any("cpuinfo" in item for item in status["missing_requirements"])
    assert any('--root "$GEOMAP_DATA_ROOT"' in item for item in status["missing_requirements"])
    assert str(data_root) not in str(result)


def test_detector_preparation_capability_is_registered_by_default(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    cache_root = tmp_path / "cache"
    data_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setenv("GEOMAP_DATA_ROOT", str(data_root))
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", str(cache_root))
    monkeypatch.setenv("GEOMAP_MCP_ALLOWED_ROOTS", f"{data_root}:{cache_root}")
    monkeypatch.delenv("GEOMAP_MCP_ENABLE_DETECTOR_PREPARATION", raising=False)
    adapter = GeomapMcpAdapter(
        registry=ResourceRegistry.from_env(base_dir=tmp_path),
        knowledge_service_factory=lambda: SimpleNamespace(_registrations=[]),
    )

    enabled = adapter.list_capabilities()["structuredContent"]["capabilities"]
    monkeypatch.setenv("GEOMAP_MCP_ENABLE_DETECTOR_PREPARATION", "false")
    disabled = adapter.list_capabilities()["structuredContent"]["capabilities"]

    assert enabled["detector_preparation"]["registered"] is True
    assert not any(
        "opt-in" in item for item in enabled["detector_preparation"]["missing_requirements"]
    )
    assert disabled["detector_preparation"]["registered"] is False
    assert any(
        "GEOMAP_MCP_ENABLE_DETECTOR_PREPARATION" in item
        for item in disabled["detector_preparation"]["missing_requirements"]
    )


def test_knowledge_preparation_capability_and_provider_remedy(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    cache_root = tmp_path / "cache"
    data_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setenv("GEOMAP_DATA_ROOT", str(data_root))
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", str(cache_root))
    monkeypatch.setenv("GEOMAP_MCP_ALLOWED_ROOTS", f"{data_root}:{cache_root}")
    monkeypatch.delenv("GEOMAP_MCP_ENABLE_KNOWLEDGE_PREPARATION", raising=False)
    service = SimpleNamespace(
        config=SimpleNamespace(
            data_root=data_root,
            knowledge_root=data_root / "assets" / "knowledge",
            resolved_k2_rock_type_path=data_root / "assets" / "knowledge" / "k2_rock_type.json",
        ),
        _registrations=[
            SimpleNamespace(
                id="rock_type",
                name="Rock type",
                output_keys=("rock_type",),
                default_enabled=True,
            )
        ],
    )
    adapter = GeomapMcpAdapter(
        registry=ResourceRegistry.from_env(base_dir=tmp_path),
        knowledge_service_factory=lambda: service,
    )

    enabled = adapter.list_capabilities()["structuredContent"]
    monkeypatch.setenv("GEOMAP_MCP_ENABLE_KNOWLEDGE_PREPARATION", "false")
    disabled = adapter.list_capabilities()["structuredContent"]

    assert enabled["capabilities"]["knowledge_preparation"]["registered"] is True
    assert any(
        "geomap_prepare_knowledge" in item
        for item in enabled["providers"][0]["missing_requirements"]
    )
    assert disabled["capabilities"]["knowledge_preparation"]["registered"] is False
    assert any(
        "server operator" in item
        for item in disabled["providers"][0]["missing_requirements"]
    )
