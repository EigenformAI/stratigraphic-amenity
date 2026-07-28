import json

import pytest
from jsonschema import ValidationError, validate

from stratigraphic_amenity.map_processing.types import (
    ArtifactRef,
    Detection,
    ImageSize,
    MapProcessingResult,
)
from stratigraphic_amenity.mcp.resources import ResourceRegistry
from stratigraphic_amenity.mcp.schemas import map_processing_result_to_mcp, tool_definitions


def _registry(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    cache_root = tmp_path / "cache"
    data_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setenv("GEOMAP_DATA_ROOT", str(data_root))
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", str(cache_root))
    monkeypatch.setenv("GEOMAP_MCP_ALLOWED_ROOTS", f"{data_root}:{cache_root}")
    return ResourceRegistry.from_env(base_dir=tmp_path), data_root, cache_root


def test_map_processing_result_conversion_redacts_path_fields(tmp_path, monkeypatch):
    registry, data_root, cache_root = _registry(tmp_path, monkeypatch)
    image_path = data_root / "source.png"
    crop_path = cache_root / "main_map_0.png"
    image_path.write_bytes(b"not inspected in this test")
    crop_path.write_bytes(b"artifact")
    map_info = registry.register_map(image_path)
    result = MapProcessingResult(
        name="source",
        source="fixture",
        image_path=image_path,
        size=ImageSize(width=100, height=80),
        regions={
            "main_map": [
                Detection(
                    label="main_map",
                    bbox=(1, 2, 50, 60),
                    confidence=0.9,
                    artifact_path=str(crop_path),
                )
            ]
        },
        artifacts=[
            ArtifactRef(
                path=crop_path,
                role="component_crop",
                stage="hie",
                bbox=(1, 2, 50, 60),
                label="main_map",
            )
        ],
    )

    converted = map_processing_result_to_mcp(result, registry=registry, map_id=map_info["map_id"])
    encoded = json.dumps(converted)

    assert "image_path" not in converted
    assert converted["source_uri"] == map_info["source_uri"]
    assert converted["regions"]["main_map"][0]["artifact_uri"].startswith(
        "geomap://artifacts/"
    )
    assert converted["artifacts"][0]["uri"].startswith("geomap://artifacts/")
    assert str(image_path) not in encoded
    assert str(crop_path) not in encoded


def test_tool_definitions_expose_stable_names_and_annotations():
    tools = {tool["name"]: tool for tool in tool_definitions()}

    assert {
        "geomap_list_capabilities",
        "geomap_register_map",
        "geomap_process_image",
        "geomap_prepare_detectors",
        "geomap_georeference",
        "geomap_query_knowledge",
        "geomap_query_map",
        "geomap_enrich_legend",
        "geomap_render_knowledge_overlay",
    } <= set(tools)
    assert tools["geomap_query_knowledge"]["annotations"]["readOnlyHint"] is False
    assert tools["geomap_query_map"]["annotations"]["readOnlyHint"] is False
    assert tools["geomap_process_image"]["annotations"]["readOnlyHint"] is False
    assert tools["geomap_prepare_detectors"]["annotations"] == {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
    }
    assert tools["geomap_register_map"]["annotations"]["readOnlyHint"] is False
    assert tools["geomap_query_knowledge"]["annotations"]["idempotentHint"] is False
    assert tools["geomap_query_map"]["annotations"]["idempotentHint"] is False
    assert tools["geomap_render_knowledge_overlay"]["annotations"]["idempotentHint"] is False
    assert tools["geomap_process_image"]["annotations"]["idempotentHint"] is False
    assert tools["geomap_georeference"]["annotations"]["idempotentHint"] is False
    for tool in tools.values():
        assert tool["inputSchema"]["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert tool["outputSchema"]["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert tool["outputSchema"]["properties"]["schema_version"]


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("geomap_process_image", {}),
        ("geomap_process_image", {"map_id": "id", "map_uri": "geomap://maps/id"}),
        ("geomap_georeference", {"crs": "EPSG:4326", "gcps": []}),
        (
            "geomap_query_knowledge",
            {"bounds": {"min_lon": -181, "min_lat": 0, "max_lon": 1, "max_lat": 1}},
        ),
        ("geomap_query_knowledge", {}),
        ("geomap_query_knowledge", {"bounds": None}),
        ("geomap_query_knowledge", {"legend_labels": []}),
        ("geomap_query_knowledge", {"query_text": ""}),
        ("geomap_query_map", {}),
        ("geomap_query_map", {"metadata": {}}),
        ("geomap_render_knowledge_overlay", {"georef": {}}),
        (
            "geomap_render_knowledge_overlay",
            {
                "bundle": {},
                "georef": {
                    "crs": "EPSG:4326",
                    "affine": {"coefficients": [1, 0, 0, 0, 1, 0]},
                    "bounds": {"min_lon": 0, "min_lat": 0, "max_lon": 1, "max_lat": 1},
                    "residual": 0,
                },
            },
        ),
        (
            "geomap_render_knowledge_overlay",
            {"bundle": {}, "bundle_uri": "geomap://bundles/id", "georef": {}},
        ),
    ],
)
def test_tool_schemas_reject_invalid_argument_combinations(tool_name, arguments):
    tools = {tool["name"]: tool for tool in tool_definitions()}

    with pytest.raises(ValidationError):
        validate(arguments, tools[tool_name]["inputSchema"])
