from stratigraphic_amenity.knowledge import KnowledgeConfig
from stratigraphic_amenity.map_processing import MapProcessingConfig
from stratigraphic_amenity.mcp.resources import ResourceRegistry


def test_installed_defaults_use_xdg_roots_not_process_cwd(tmp_path, monkeypatch):
    launch = tmp_path / "arbitrary-launch"
    xdg_data = tmp_path / "xdg-data"
    xdg_cache = tmp_path / "xdg-cache"
    launch.mkdir()
    monkeypatch.chdir(launch)
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data))
    monkeypatch.setenv("XDG_CACHE_HOME", str(xdg_cache))
    for name in (
        "GEOMAP_DATA_ROOT",
        "GEOMAP_MODEL_ROOT",
        "GEOMAP_KNOWLEDGE_ROOT",
        "GEOMAP_KNOWLEDGE_SOURCES_ROOT",
        "GEOMAP_CACHE_ROOT",
        "GEOMAP_MCP_ALLOWED_ROOTS",
    ):
        monkeypatch.delenv(name, raising=False)

    map_config = MapProcessingConfig.from_env()
    knowledge_config = KnowledgeConfig.from_env()
    registry = ResourceRegistry.from_env()

    expected_data = xdg_data / "stratigraphic-amenity"
    expected_cache = xdg_cache / "stratigraphic-amenity"
    assert map_config.data_root == expected_data
    assert map_config.model_root == expected_data / "assets" / "models"
    assert map_config.resolved_ultralytics_root == expected_data / "assets" / "runtime" / "ultralytics"
    assert map_config.cache_root == expected_cache
    assert knowledge_config.data_root == expected_data
    assert knowledge_config.knowledge_root == expected_data / "assets" / "knowledge"
    assert knowledge_config.cache_root == expected_cache
    assert registry.data_root == expected_data
    assert registry.cache_root == expected_cache
    assert launch not in registry.allowed_roots


def test_explicit_relative_roots_resolve_from_launch_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOMAP_DATA_ROOT", "relative-data")
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", "relative-cache")
    for name in (
        "GEOMAP_MODEL_ROOT",
        "GEOMAP_ULTRALYTICS_ROOT",
        "GEOMAP_KNOWLEDGE_ROOT",
        "GEOMAP_KNOWLEDGE_SOURCES_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)

    map_config = MapProcessingConfig.from_env(base_dir=tmp_path)
    knowledge_config = KnowledgeConfig.from_env(base_dir=tmp_path)

    expected_data = tmp_path / "relative-data"
    assert map_config.data_root == expected_data
    assert map_config.model_root == expected_data / "assets" / "models"
    assert map_config.resolved_ultralytics_root == expected_data / "assets" / "runtime" / "ultralytics"
    assert map_config.cache_root == tmp_path / "relative-cache"
    assert knowledge_config.data_root == expected_data
    assert knowledge_config.knowledge_root == expected_data / "assets" / "knowledge"
    assert knowledge_config.knowledge_sources_root == expected_data / "knowledge" / "sources"
