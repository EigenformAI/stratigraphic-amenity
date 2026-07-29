from pathlib import Path

import pytest

from stratigraphic_amenity.asset_installer import InstallResult
from stratigraphic_amenity.knowledge.config import KnowledgeConfig
from stratigraphic_amenity.knowledge.preparation import (
    KNOWLEDGE_ASSET_IDS,
    KnowledgePreparationError,
    prepare_knowledge,
)
from stratigraphic_amenity.mcp import adapter as adapter_module
from stratigraphic_amenity.mcp.errors import McpToolError


def _config(tmp_path: Path) -> KnowledgeConfig:
    data_root = tmp_path / "data"
    return KnowledgeConfig(
        data_root=data_root,
        knowledge_root=data_root / "assets" / "knowledge",
        cache_root=tmp_path / "cache",
    )


def test_prepare_knowledge_installs_only_fixed_manifest_asset(tmp_path):
    calls = []

    def provision(asset_ids, *, root, force=False):
        calls.append((tuple(asset_ids), root, force))
        return [
            InstallResult(asset_id, "installed", Path(root) / asset_id)
            for asset_id in asset_ids
        ]

    result = prepare_knowledge(_config(tmp_path), provision=provision)

    assert calls == [(KNOWLEDGE_ASSET_IDS, tmp_path / "data", False)]
    assert result.assets == ({"asset_id": "peace-knowledge-base", "status": "installed"},)


def test_prepare_knowledge_rejects_custom_knowledge_paths(tmp_path):
    config = _config(tmp_path)
    config.k2_rock_type_path = tmp_path / "custom" / "rock-types.json"

    with pytest.raises(KnowledgePreparationError, match="manifest destinations"):
        prepare_knowledge(config, provision=lambda *_args, **_kwargs: [])


def _stub_preparation(monkeypatch):
    from stratigraphic_amenity.knowledge.preparation import KnowledgePreparationResult

    monkeypatch.setattr(
        adapter_module,
        "prepare_knowledge",
        lambda _config: KnowledgePreparationResult(
            assets=({"asset_id": "peace-knowledge-base", "status": "installed"},)
        ),
    )


def test_adapter_prepare_knowledge_reports_post_install_readiness(tmp_path, monkeypatch):
    monkeypatch.delenv("GEOMAP_MCP_ENABLE_KNOWLEDGE_PREPARATION", raising=False)
    monkeypatch.setenv("GEOMAP_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", str(tmp_path / "cache"))
    _stub_preparation(monkeypatch)

    result = adapter_module.GeomapMcpAdapter().prepare_knowledge()
    structured = result["structuredContent"]

    assert structured["assets"]
    assert "providers" in structured
    assert structured["performs_network_access"] is True
    assert "provider" in structured["text_summary"].lower()
    ready_ids = [provider["id"] for provider in structured["providers"] if provider["ready"]]
    assert ready_ids
    assert all(provider_id in structured["text_summary"] for provider_id in ready_ids)
    assert "retry" in structured["text_summary"].lower()
    assert result["content"][0]["text"] == structured["text_summary"]


def test_adapter_prepare_knowledge_refuses_when_opted_out(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOMAP_MCP_ENABLE_KNOWLEDGE_PREPARATION", "false")
    monkeypatch.setenv("GEOMAP_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", str(tmp_path / "cache"))
    _stub_preparation(monkeypatch)

    with pytest.raises(McpToolError) as excinfo:
        adapter_module.GeomapMcpAdapter().prepare_knowledge()

    assert excinfo.value.code == "preparation_disabled"
