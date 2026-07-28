import asyncio
import base64

import pytest

from stratigraphic_amenity.mcp.adapter import GeomapMcpAdapter
from stratigraphic_amenity.mcp.errors import McpToolError
from stratigraphic_amenity.mcp.resources import ResourceRegistry
from stratigraphic_amenity.mcp.server import create_server


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGA"
    "WjR9awAAAABJRU5ErkJggg=="
)


class FailingAdapter:
    def list_capabilities(self):
        raise McpToolError(
            code="disallowed_path",
            message="Path is outside allowed roots.",
            trace_id="trace-fixture",
            details={"path_label": "outside-root"},
            recovery_hints=["Choose a path under GEOMAP_MCP_ALLOWED_ROOTS."],
        )


class InvalidOutputAdapter:
    def list_capabilities(self):
        return {"content": [], "structuredContent": {"trace_id": "bad-output"}}


def _registry(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    cache_root = tmp_path / "cache"
    data_root.mkdir()
    cache_root.mkdir()
    monkeypatch.setenv("GEOMAP_DATA_ROOT", str(data_root))
    monkeypatch.setenv("GEOMAP_CACHE_ROOT", str(cache_root))
    monkeypatch.setenv("GEOMAP_MCP_ALLOWED_ROOTS", f"{data_root}:{cache_root}")
    return ResourceRegistry.from_env(base_dir=tmp_path), data_root, cache_root


def _dispatch(server, name, arguments):
    import mcp.types as mcp_types

    handler = server.request_handlers[mcp_types.CallToolRequest]

    async def invoke():
        return await handler(
            mcp_types.CallToolRequest(
                method="tools/call",
                params={"name": name, "arguments": arguments},
            )
        )

    return asyncio.run(invoke()).model_dump()


def test_call_tool_preserves_typed_errors_over_server_handler():
    pytest.importorskip("mcp.types")
    server = create_server(adapter=FailingAdapter())
    result = _dispatch(server, "geomap_list_capabilities", {})

    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "disallowed_path"
    assert result["structuredContent"]["schema_version"] == "geomap-error/v1"
    assert result["structuredContent"]["error"]["trace_id"] == "trace-fixture"
    assert result["structuredContent"]["error"]["details"] == {"path_label": "outside-root"}
    assert result["structuredContent"]["error"]["recovery_hints"] == [
        "Choose a path under GEOMAP_MCP_ALLOWED_ROOTS."
    ]
    assert result["structuredContent"]["code"] == "disallowed_path"


def test_input_validation_error_is_structured_and_traced():
    pytest.importorskip("mcp.types")
    server = create_server(adapter=FailingAdapter())
    # The unknown "bogus" property violates additionalProperties: False.
    result = _dispatch(server, "geomap_register_map", {"path": "/x", "bogus": 1})

    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "invalid_arguments"
    assert result["structuredContent"]["error"]["trace_id"]
    assert result["structuredContent"]["text_summary"]


def test_unknown_tool_is_structured_error():
    pytest.importorskip("mcp.types")
    server = create_server(adapter=FailingAdapter())
    result = _dispatch(server, "geomap_does_not_exist", {})

    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "unknown_tool"
    assert result["structuredContent"]["error"]["trace_id"]


def test_invalid_adapter_output_is_a_typed_error():
    pytest.importorskip("mcp.types")
    server = create_server(adapter=InvalidOutputAdapter())

    result = _dispatch(server, "geomap_list_capabilities", {})

    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "invalid_output"
    assert result["structuredContent"]["error"]["trace_id"] == "bad-output"


def test_registry_error_through_handler_carries_trace_id(tmp_path, monkeypatch):
    pytest.importorskip("mcp.types")
    registry, _, _ = _registry(tmp_path, monkeypatch)
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG_1X1)
    server = create_server(adapter=GeomapMcpAdapter(registry=registry))

    result = _dispatch(server, "geomap_register_map", {"path": str(outside)})

    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "disallowed_path"
    # Registry errors are trace-agnostic; the adapter call stamps its own trace id.
    assert result["structuredContent"]["error"]["trace_id"]


def test_adapter_stamps_method_trace_on_registry_error(tmp_path, monkeypatch):
    registry, _, _ = _registry(tmp_path, monkeypatch)
    adapter = GeomapMcpAdapter(registry=registry)

    with pytest.raises(McpToolError) as exc_info:
        adapter.process_image(map_id="does-not-exist")

    assert exc_info.value.code == "artifact_not_found"
    assert exc_info.value.trace_id is not None


def test_tool_diagnostics_are_redacted_and_written_to_stderr(monkeypatch, capsys):
    pytest.importorskip("mcp.types")
    monkeypatch.setenv("GEOMAP_LOG_LEVEL", "INFO")
    server = create_server(adapter=FailingAdapter())

    _dispatch(server, "geomap_list_capabilities", {})

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "tool=geomap_list_capabilities" in captured.err
    assert "outcome=disallowed_path" in captured.err
    assert "trace_id=trace-fixture" in captured.err
    assert "Path is outside" not in captured.err
