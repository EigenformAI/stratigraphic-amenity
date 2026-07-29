import json

import pytest

from stratigraphic_amenity.knowledge import Bounds, KnowledgeConfig, KnowledgeService
from stratigraphic_amenity.knowledge.errors import MissingAssetError, OptionalDependencyError
from stratigraphic_amenity.knowledge.service import ProviderRegistration
from stratigraphic_amenity.knowledge.types import KnowledgeItem
from stratigraphic_amenity.mcp.adapter import GeomapMcpAdapter
from stratigraphic_amenity.mcp.errors import McpToolError
from stratigraphic_amenity.mcp.resources import ResourceRegistry


class EchoProvider:
    id = "echo"
    name = "Echo"
    output_keys = ("echo",)
    version = "fixture-v1"
    last_warnings: list[str] = []

    def __init__(self, captured, secret_path):
        self.captured = captured
        self.secret_path = secret_path

    def supports(self, request):
        return True

    def validate_options(self, options):
        return dict(options)

    def query(self, request):
        self.captured["request"] = request
        return [
            KnowledgeItem(
                id="echo-1",
                key="echo",
                provider="echo",
                value={"legend_labels": list(request.legend_labels)},
                summary="echo summary",
                source=str(self.secret_path),
                record_count=1,
                provenance={"asset_path": str(self.secret_path)},
            )
        ]


def _adapter(tmp_path, monkeypatch, captured):
    data_root = tmp_path / "data"
    cache_root = tmp_path / "cache"
    data_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setenv("GEOMAP_DATA_ROOT", str(data_root))
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", str(cache_root))
    monkeypatch.setenv("GEOMAP_MCP_ALLOWED_ROOTS", f"{data_root}:{cache_root}")
    registry = ResourceRegistry.from_env(base_dir=tmp_path)
    provider = EchoProvider(captured, tmp_path / "secret" / "asset.json")
    config = KnowledgeConfig(
        data_root=data_root,
        knowledge_root=tmp_path / "knowledge",
        cache_root=cache_root,
        write_cache=False,
    )
    service = KnowledgeService(config=config, providers=[provider])
    return GeomapMcpAdapter(registry=registry, knowledge_service_factory=lambda: service)


class CountProvider:
    """Returns one summary item that carries many records (truncated)."""

    id = "minerals_fixture"
    name = "Minerals Fixture"
    output_keys = ("minerals_fixture",)
    version = "fixture-v1"
    last_warnings: list[str] = []

    def supports(self, request):
        return True

    def validate_options(self, options):
        return dict(options)

    def query(self, request):
        return [
            KnowledgeItem(
                id="m-1",
                key="minerals_fixture",
                provider="minerals_fixture",
                value=[{"n": i} for i in range(50)],
                summary="found 86, returning 50",
                record_count=86,
                truncated=True,
            )
        ]


def _adapter_with(tmp_path, monkeypatch, provider):
    data_root = tmp_path / "data"
    cache_root = tmp_path / "cache"
    data_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setenv("GEOMAP_DATA_ROOT", str(data_root))
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", str(cache_root))
    monkeypatch.setenv("GEOMAP_MCP_ALLOWED_ROOTS", f"{data_root}:{cache_root}")
    registry = ResourceRegistry.from_env(base_dir=tmp_path)
    config = KnowledgeConfig(
        data_root=data_root,
        knowledge_root=tmp_path / "knowledge",
        cache_root=cache_root,
        write_cache=False,
    )
    service = KnowledgeService(config=config, providers=[provider])
    return GeomapMcpAdapter(registry=registry, knowledge_service_factory=lambda: service)


def _adapter_with_registrations(tmp_path, monkeypatch, registrations):
    adapter = _adapter_with(tmp_path, monkeypatch, CountProvider())
    config = adapter._knowledge().config
    service = KnowledgeService(config=config, provider_registrations=registrations)
    adapter._knowledge_service = service
    return adapter


def test_bundle_summary_reports_record_yield_not_item_count(tmp_path, monkeypatch):
    adapter = _adapter_with(tmp_path, monkeypatch, CountProvider())

    result = adapter.query_knowledge(
        bounds={"min_lon": -91, "min_lat": 48, "max_lon": -90, "max_lat": 49},
        include=["minerals_fixture"],
    )
    structured = result["structuredContent"]

    # Machine-readable yield, so an agent need not sum item.value itself.
    assert structured["total_records_found"] == 86
    assert structured["total_records_returned"] == 50
    assert structured["record_counts"]["minerals_fixture"] == 86
    assert structured["truncated"] is True

    # The human summary must surface the real yield, not the misleading item count.
    summary = structured["text_summary"]
    assert "86" in summary
    assert "minerals_fixture=86" in summary
    assert "1 item" not in summary


def test_bundle_summary_handles_zero_record_providers(tmp_path, monkeypatch):
    class EmptyProvider(CountProvider):
        def query(self, request):
            return [
                KnowledgeItem(
                    id="e-1",
                    key="minerals_fixture",
                    provider="minerals_fixture",
                    value=[],
                    summary="nothing in bounds",
                    record_count=0,
                )
            ]

    adapter = _adapter_with(tmp_path, monkeypatch, EmptyProvider())
    result = adapter.query_knowledge(
        bounds={"min_lon": -91, "min_lat": 48, "max_lon": -90, "max_lat": 49},
        include=["minerals_fixture"],
    )
    structured = result["structuredContent"]
    assert structured["total_records_found"] == 0
    assert structured["total_records_returned"] == 0
    assert structured["truncated"] is False
    assert "0 record" in structured["text_summary"]


def test_bundle_summary_repeats_warning_text_for_text_only_clients(tmp_path, monkeypatch):
    warnings = [
        "The source does not cover these bounds.",
        "An empty result is not evidence of geological absence.",
    ]

    class WarningProvider(CountProvider):
        def query(self, request):
            self.last_warnings = warnings
            return super().query(request)

    adapter = _adapter_with(tmp_path, monkeypatch, WarningProvider())
    result = adapter.query_knowledge(
        bounds={"min_lon": -91, "min_lat": 48, "max_lon": -90, "max_lat": 49},
        include=["minerals_fixture"],
    )
    structured = result["structuredContent"]

    assert structured["warnings"] == warnings
    assert all(warning in structured["text_summary"] for warning in warnings)
    assert result["content"][0]["text"] == structured["text_summary"]


def test_bundle_summary_scrubs_paths_embedded_in_warnings(tmp_path, monkeypatch):
    secret = tmp_path / "private" / "earthquakes.csv"

    class WarningProvider(CountProvider):
        def query(self, request):
            self.last_warnings = [f"Knowledge asset does not exist: {secret}"]
            return super().query(request)

    adapter = _adapter_with(tmp_path, monkeypatch, WarningProvider())
    result = adapter.query_knowledge(
        bounds={"min_lon": -91, "min_lat": 48, "max_lon": -90, "max_lat": 49},
        include=["minerals_fixture"],
    )
    structured = result["structuredContent"]

    assert str(tmp_path) not in json.dumps(result)
    assert "Knowledge asset does not exist: <redacted>" in structured["warnings"][0]
    persisted = adapter.read_resource(structured["bundle_uri"])
    assert str(tmp_path) not in persisted["text"]


def test_partial_missing_asset_warning_recommends_preparation(tmp_path, monkeypatch):
    class MissingProvider(CountProvider):
        id = "missing_fixture"
        name = "Missing Fixture"
        output_keys = ("missing_fixture",)

        def query(self, request):
            raise MissingAssetError(f"Missing asset: {tmp_path / 'private.json'}")

    providers = [CountProvider(), MissingProvider()]
    registrations = [
        ProviderRegistration(
            id=provider.id,
            name=provider.name,
            output_keys=provider.output_keys,
            factory=lambda provider=provider: provider,
            supports=provider.supports,
            supported_requests=("bounds",),
        )
        for provider in providers
    ]
    adapter = _adapter_with_registrations(tmp_path, monkeypatch, registrations)

    result = adapter.query_knowledge(
        bounds={"min_lon": -91, "min_lat": 48, "max_lon": -90, "max_lat": 49},
        include=["minerals_fixture", "missing_fixture"],
    )
    structured = result["structuredContent"]

    assert structured["total_records_found"] == 86
    assert "missing_fixture" in structured["text_summary"]
    assert "geomap_prepare_knowledge" in structured["text_summary"]
    assert str(tmp_path) not in json.dumps(result)


def test_implicit_missing_asset_warning_escalates_when_preparation_is_hidden(
    tmp_path, monkeypatch
):
    class MissingProvider(CountProvider):
        id = "missing_fixture"
        name = "Missing Fixture"
        output_keys = ("missing_fixture",)

        def query(self, request):
            raise MissingAssetError("Missing asset")

    provider = MissingProvider()
    registration = ProviderRegistration(
        id=provider.id,
        name=provider.name,
        output_keys=provider.output_keys,
        factory=lambda: provider,
        supports=provider.supports,
        supported_requests=("bounds",),
    )
    monkeypatch.setenv("GEOMAP_MCP_ENABLE_KNOWLEDGE_PREPARATION", "false")
    adapter = _adapter_with_registrations(tmp_path, monkeypatch, [registration])

    result = adapter.query_knowledge(
        bounds={"min_lon": -91, "min_lat": 48, "max_lon": -90, "max_lat": 49}
    )
    summary = result["structuredContent"]["text_summary"]

    assert "missing_fixture" in summary
    assert "server operator" in summary
    assert "geomap_prepare_knowledge" not in summary


def test_default_query_reports_compatible_provider_not_consulted(tmp_path, monkeypatch):
    provider = CountProvider()
    registration = ProviderRegistration(
        id=provider.id,
        name=provider.name,
        output_keys=provider.output_keys,
        factory=lambda: provider,
        supports=provider.supports,
        supported_requests=("bounds",),
        default_enabled=False,
    )
    adapter = _adapter_with_registrations(tmp_path, monkeypatch, [registration])

    result = adapter.query_knowledge(
        bounds={"min_lon": -91, "min_lat": 48, "max_lon": -90, "max_lat": 49}
    )
    summary = result["structuredContent"]["text_summary"]

    assert "minerals_fixture" in summary
    assert "not consulted" in summary
    assert 'include=["minerals_fixture"]' in summary


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (MissingAssetError("Knowledge asset does not exist: /server/private/asset.json"), "missing_knowledge_asset"),
        (OptionalDependencyError("Install secret-package from /server/private"), "missing_extra"),
    ],
)
def test_knowledge_readiness_errors_are_actionable_and_scrubbed(
    tmp_path, monkeypatch, error, code
):
    class FailingProvider(CountProvider):
        def query(self, request):
            raise error

    adapter = _adapter_with(tmp_path, monkeypatch, FailingProvider())

    with pytest.raises(McpToolError) as excinfo:
        adapter.query_knowledge(
            bounds={"min_lon": -91, "min_lat": 48, "max_lon": -90, "max_lat": 49},
            include=["minerals_fixture"],
        )

    assert excinfo.value.code == code
    assert "server" in excinfo.value.message.lower()
    assert "/server/private" not in json.dumps(excinfo.value.to_dict())
    if isinstance(error, MissingAssetError):
        assert "geomap_prepare_knowledge" in excinfo.value.message


def test_missing_knowledge_asset_escalates_when_preparation_is_hidden(tmp_path, monkeypatch):
    class FailingProvider(CountProvider):
        def query(self, request):
            raise MissingAssetError("missing")

    monkeypatch.setenv("GEOMAP_MCP_ENABLE_KNOWLEDGE_PREPARATION", "false")
    adapter = _adapter_with(tmp_path, monkeypatch, FailingProvider())

    with pytest.raises(McpToolError) as excinfo:
        adapter.query_knowledge(
            bounds={"min_lon": -91, "min_lat": 48, "max_lon": -90, "max_lat": 49},
            include=["minerals_fixture"],
        )

    assert "server operator" in excinfo.value.message.lower()
    assert "geomap_prepare_knowledge" not in excinfo.value.message


def test_enrich_legend_translates_missing_knowledge_assets(tmp_path, monkeypatch):
    adapter = _adapter_with(tmp_path, monkeypatch, CountProvider())

    class MissingLegendService:
        def enrich_legend_label(self, label):
            raise MissingAssetError(f"Missing label asset: {tmp_path / 'private.json'}")

    adapter._knowledge_service = MissingLegendService()

    with pytest.raises(McpToolError) as excinfo:
        adapter.enrich_legend("gneiss")

    assert excinfo.value.code == "missing_knowledge_asset"
    assert str(tmp_path) not in json.dumps(excinfo.value.to_dict())


def test_query_knowledge_preserves_full_request_and_persists_bundle(tmp_path, monkeypatch):
    captured = {}
    adapter = _adapter(tmp_path, monkeypatch, captured)

    result = adapter.query_knowledge(
        bounds={"min_lon": -122, "min_lat": 37, "max_lon": -121, "max_lat": 38},
        legend_labels=["sandstone"],
        query_text="what is here?",
        include=["echo"],
        exclude=["unused"],
        max_records=5,
        max_records_by_provider={"echo": 3},
        provider_options={"echo": {"mode": "fixture"}},
    )

    request = captured["request"]
    assert isinstance(request.bounds, Bounds)
    assert request.legend_labels == ["sandstone"]
    assert request.query_text == "what is here?"
    assert request.include == ("echo",)
    assert request.exclude == ("unused",)
    assert request.max_records == 5
    assert request.max_records_by_provider == {"echo": 3}
    assert request.provider_options == {"echo": {"mode": "fixture"}}

    structured = result["structuredContent"]
    assert structured["bundle_uri"].startswith("geomap://bundles/")
    assert structured["items"][0]["source"] == "<redacted>"
    assert structured["items"][0]["provenance"]["asset_path"] == "<redacted>"
    assert str(tmp_path) not in json.dumps(result)

    bundle_resource = adapter.read_resource(structured["bundle_uri"])
    assert bundle_resource["mimeType"] == "application/json"
    assert json.loads(bundle_resource["text"])["items"][0]["id"] == "echo-1"
