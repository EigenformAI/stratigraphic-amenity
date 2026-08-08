import base64
from concurrent.futures import ThreadPoolExecutor
import json
import random
from threading import Barrier
import time

import pytest

from stratigraphic_amenity.mcp.errors import McpToolError
from stratigraphic_amenity.mcp.resources import ResourceRegistry


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGA"
    "WjR9awAAAABJRU5ErkJggg=="
)


def _registry(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    cache_root = tmp_path / "cache"
    data_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setenv("GEOMAP_DATA_ROOT", str(data_root))
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", str(cache_root))
    monkeypatch.setenv(
        "GEOMAP_MCP_ALLOWED_ROOTS",
        f"{data_root}:{cache_root}",
    )
    return ResourceRegistry.from_env(base_dir=tmp_path), data_root, cache_root


def test_register_map_is_idempotent_and_redacts_source_path(tmp_path, monkeypatch):
    registry, data_root, _ = _registry(tmp_path, monkeypatch)
    image_path = data_root / "map.png"
    image_path.write_bytes(PNG_1X1)

    first = registry.register_map(image_path)
    second = registry.register_map(image_path)

    assert first["map_id"] == second["map_id"]
    assert first["map_uri"] == f"geomap://maps/{first['map_id']}"
    assert first["source_uri"] == f"geomap://maps/{first['map_id']}/source"
    assert str(image_path) not in json.dumps(first)

    content = registry.read_resource(first["source_uri"])
    assert content["uri"] == first["source_uri"]
    assert content["mimeType"] == "image/png"
    assert base64.b64decode(content["blob"]) == PNG_1X1


def test_registry_rejects_paths_outside_allowed_roots(tmp_path, monkeypatch):
    registry, _, _ = _registry(tmp_path, monkeypatch)
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG_1X1)

    with pytest.raises(McpToolError) as exc_info:
        registry.register_map(outside)

    assert exc_info.value.code == "disallowed_path"
    assert exc_info.value.details["basename"] == outside.name
    assert exc_info.value.details["path_origin"] == "input_image"
    assert str(outside.parent) not in str(exc_info.value.details)


def test_registry_rejects_symlink_escape(tmp_path, monkeypatch):
    registry, data_root, _ = _registry(tmp_path, monkeypatch)
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG_1X1)
    link = data_root / "linked.png"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable on this filesystem")

    with pytest.raises(McpToolError) as exc_info:
        registry.register_map(link)

    assert exc_info.value.code == "disallowed_path"


def test_deferred_save_coalesces_writes(tmp_path, monkeypatch):
    registry, _, cache_root = _registry(tmp_path, monkeypatch)
    paths = []
    for index in range(3):
        path = cache_root / f"crop_{index}.png"
        path.write_bytes(PNG_1X1)
        paths.append(path)

    calls = {"count": 0}
    original_write = registry._write

    def counting_write():
        calls["count"] += 1
        original_write()

    monkeypatch.setattr(registry, "_write", counting_write)

    with registry.deferred_save():
        for path in paths:
            registry.register_artifact(path, role="component_crop", stage="hie")
    assert calls["count"] == 1

    # Each registration outside a deferred scope writes once on its own.
    calls["count"] = 0
    extra = cache_root / "crop_extra.png"
    extra.write_bytes(PNG_1X1)
    registry.register_artifact(extra, role="component_crop", stage="hie")
    assert calls["count"] == 1

    # All four artifacts survived the coalesced and direct writes.
    reloaded = ResourceRegistry.from_env(base_dir=tmp_path)
    assert len(reloaded._data["artifacts"]) == 4


def test_reading_stale_artifact_returns_typed_error(tmp_path, monkeypatch):
    registry, _, cache_root = _registry(tmp_path, monkeypatch)
    artifact_path = cache_root / "overlay.png"
    artifact_path.write_bytes(PNG_1X1)
    artifact = registry.register_artifact(artifact_path, role="detection_overlay", stage="hie")
    artifact_path.unlink()

    with pytest.raises(McpToolError) as exc_info:
        registry.read_resource(artifact["uri"])

    assert exc_info.value.code == "artifact_not_found"


def test_registry_rejects_unsupported_and_oversize_sources(tmp_path, monkeypatch):
    _, data_root, cache_root = _registry(tmp_path, monkeypatch)
    text_path = data_root / "map.txt"
    image_path = data_root / "map.png"
    text_path.write_text("not an image", encoding="utf-8")
    image_path.write_bytes(PNG_1X1)
    registry = ResourceRegistry(
        data_root=data_root,
        cache_root=cache_root,
        allowed_roots=[data_root, cache_root],
        max_source_bytes=1,
    )

    with pytest.raises(McpToolError, match="Unsupported") as unsupported:
        registry.register_map(text_path)
    with pytest.raises(McpToolError) as oversize:
        registry.register_map(image_path)

    assert unsupported.value.code == "unsupported_media"
    assert oversize.value.code == "oversize_image"


def test_registry_enforces_resource_read_limit(tmp_path, monkeypatch):
    _, data_root, cache_root = _registry(tmp_path, monkeypatch)
    registry = ResourceRegistry(
        data_root=data_root,
        cache_root=cache_root,
        allowed_roots=[data_root, cache_root],
        max_resource_read_bytes=1,
    )
    artifact_path = cache_root / "large.png"
    artifact_path.write_bytes(PNG_1X1)
    artifact = registry.register_artifact(artifact_path, role="component_crop", stage="hie")

    with pytest.raises(McpToolError) as exc_info:
        registry.read_resource(artifact["uri"])

    assert exc_info.value.code == "oversize_image"
    assert exc_info.value.details == {
        "observed_bytes": len(PNG_1X1),
        "limit_bytes": 1,
    }
    assert exc_info.value.recovery_hints


def test_artifact_path_cannot_change_map_ownership(tmp_path, monkeypatch):
    registry, _, cache_root = _registry(tmp_path, monkeypatch)
    path = cache_root / "crop.png"
    path.write_bytes(PNG_1X1)
    registry.register_artifact(path, role="component_crop", stage="hie", map_id="map-a")

    with pytest.raises(McpToolError) as exc_info:
        registry.register_artifact(path, role="component_crop", stage="hie", map_id="map-b")

    assert exc_info.value.code == "internal_error"
    assert str(path) not in str(exc_info.value.to_dict())


def test_explicit_source_roots_still_allow_registry_owned_cache_resources(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    cache_root = tmp_path / "cache"
    data_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setenv("GEOMAP_DATA_ROOT", str(data_root))
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", str(cache_root))
    monkeypatch.setenv("GEOMAP_MCP_ALLOWED_ROOTS", str(data_root))
    registry = ResourceRegistry.from_env(base_dir=tmp_path)
    image = data_root / "map.png"
    image.write_bytes(PNG_1X1)
    map_info = registry.register_map(image)
    artifact_path = cache_root / "crop.png"
    artifact_path.write_bytes(PNG_1X1)
    artifact = registry.register_artifact(
        artifact_path, role="component_crop", stage="hie", map_id=map_info["map_id"]
    )
    georef = registry.set_map_georef(map_info["map_id"], {"schema_version": "georef/v1"})

    assert registry.read_resource(artifact["uri"])["blob"]
    assert registry.read_resource(georef["uri"])["text"]
    assert registry.read_resource(map_info["map_uri"])["text"]


def test_map_georeferences_are_versioned_and_current_alias_tracks_latest(tmp_path, monkeypatch):
    registry, data_root, _ = _registry(tmp_path, monkeypatch)
    image = data_root / "map.png"
    image.write_bytes(PNG_1X1)
    map_info = registry.register_map(image)

    first = registry.set_map_georef(map_info["map_id"], {"gcp_count": 4})
    second = registry.set_map_georef(map_info["map_id"], {"gcp_count": 2})

    assert first["uri"].endswith("/georef/1.json")
    assert second["uri"].endswith("/georef/2.json")
    assert json.loads(registry.read_resource(first["uri"])["text"])["gcp_count"] == 4
    assert json.loads(registry.read_resource(second["uri"])["text"])["gcp_count"] == 2
    current_uri = f"{map_info['map_uri']}/georef.json"
    assert json.loads(registry.read_resource(current_uri)["text"])["gcp_count"] == 2
    assert registry.get_map_georef(map_info["map_id"])["gcp_count"] == 2


def test_corrupt_registry_fails_closed_with_recovery_hint(tmp_path, monkeypatch):
    _, _, cache_root = _registry(tmp_path, monkeypatch)
    registry_path = cache_root / "mcp" / "v1" / "registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(McpToolError) as exc_info:
        ResourceRegistry.from_env(base_dir=tmp_path)

    assert exc_info.value.code == "registry_corrupt"
    assert exc_info.value.recovery_hints
    assert str(registry_path) not in exc_info.value.message


def test_concurrent_registry_writes_preserve_all_maps_with_jitter(tmp_path, monkeypatch):
    _, data_root, _ = _registry(tmp_path, monkeypatch)
    paths = []
    for index in range(20):
        path = data_root / f"map-{index}.png"
        path.write_bytes(PNG_1X1)
        paths.append(path)

    def register(path):
        time.sleep(random.uniform(0, 0.02))
        return ResourceRegistry.from_env(base_dir=tmp_path).register_map(path)["map_id"]

    with ThreadPoolExecutor(max_workers=8) as executor:
        map_ids = list(executor.map(register, paths))

    reloaded = ResourceRegistry.from_env(base_dir=tmp_path)
    assert len(set(map_ids)) == len(paths)
    assert len(reloaded._data["maps"]) == len(paths)


def test_concurrent_georeferences_receive_distinct_immutable_revisions(tmp_path, monkeypatch):
    registry, data_root, _ = _registry(tmp_path, monkeypatch)
    image = data_root / "map.png"
    image.write_bytes(PNG_1X1)
    map_info = registry.register_map(image)
    registries = [ResourceRegistry.from_env(base_dir=tmp_path) for _ in range(8)]
    barrier = Barrier(len(registries))

    def georeference(item):
        index, concurrent_registry = item
        barrier.wait()
        return concurrent_registry.set_map_georef(map_info["map_id"], {"fit": index})

    with ThreadPoolExecutor(max_workers=len(registries)) as executor:
        resources = list(executor.map(georeference, enumerate(registries)))

    assert len({resource["uri"] for resource in resources}) == len(resources)
    reloaded = ResourceRegistry.from_env(base_dir=tmp_path)
    stored_fits = {
        json.loads(reloaded.read_resource(resource["uri"])["text"])["fit"]
        for resource in resources
    }
    assert stored_fits == set(range(len(registries)))


def test_list_resources_returns_concrete_redacted_uris(tmp_path, monkeypatch):
    registry, data_root, cache_root = _registry(tmp_path, monkeypatch)
    image = data_root / "map.png"
    image.write_bytes(PNG_1X1)
    map_info = registry.register_map(image)
    crop = cache_root / "crop.png"
    crop.write_bytes(PNG_1X1)
    artifact = registry.register_artifact(
        crop,
        role="component_crop",
        stage="hie",
        map_id=map_info["map_id"],
        bbox=[1, 2, 30, 40],
        label="main_map",
    )
    georef = registry.set_map_georef(map_info["map_id"], {"schema_version": "georef/v1"})

    resources = registry.list_resources()
    serialized = json.dumps(resources)
    uris = {item["uri"] for item in resources}

    assert map_info["map_uri"] in uris
    assert map_info["source_uri"] in uris
    assert artifact["uri"] in uris
    assert georef["uri"] in uris
    artifact_descriptor = next(item for item in resources if item["uri"] == artifact["uri"])
    assert "component_crop" in artifact_descriptor["name"]
    assert map_info["map_id"] in artifact_descriptor["description"]
    assert "label=main_map" in artifact_descriptor["description"]
    assert "bbox=[1, 2, 30, 40]" in artifact_descriptor["description"]
    assert "source_path" not in serialized
    assert str(tmp_path) not in serialized


def test_list_resources_marks_entries_that_exceed_read_limit(tmp_path, monkeypatch):
    _, data_root, cache_root = _registry(tmp_path, monkeypatch)
    registry = ResourceRegistry(
        data_root=data_root,
        cache_root=cache_root,
        allowed_roots=[data_root, cache_root],
        max_resource_read_bytes=1,
    )
    image = data_root / "map.png"
    image.write_bytes(PNG_1X1)
    map_info = registry.register_map(image)
    crop = cache_root / "crop.png"
    crop.write_bytes(PNG_1X1)
    artifact = registry.register_artifact(
        crop, role="component_crop", stage="hie", map_id=map_info["map_id"]
    )

    resources = {item["uri"]: item for item in registry.list_resources()}

    for uri in (map_info["source_uri"], artifact["uri"]):
        descriptor = resources[uri]
        assert descriptor["name"].startswith("UNREADABLE ")
        assert "exceeds max_resource_read_bytes" in descriptor["description"]
        assert f"observed_bytes={len(PNG_1X1)}" in descriptor["description"]
        assert "limit_bytes=1" in descriptor["description"]


def test_list_resources_omits_stale_files(tmp_path, monkeypatch):
    registry, _, cache_root = _registry(tmp_path, monkeypatch)
    crop = cache_root / "crop.png"
    crop.write_bytes(PNG_1X1)
    artifact = registry.register_artifact(crop, role="component_crop", stage="hie")
    crop.unlink()

    assert artifact["uri"] not in {item["uri"] for item in registry.list_resources()}
