import asyncio
import base64
import os
import sys
from pathlib import Path

import pytest


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGA"
    "WjR9awAAAABJRU5ErkJggg=="
)
ROOT = Path(__file__).resolve().parents[1]


def test_real_stdio_asset_free_workflow(tmp_path):
    pytest.importorskip("mcp")
    pytest.importorskip("pyproj")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    data_root = tmp_path / "data"
    cache_root = tmp_path / "cache"
    data_root.mkdir()
    cache_root.mkdir()
    image = data_root / "map.png"
    image.write_bytes(PNG_1X1)
    environment = os.environ.copy()
    environment.update(
        {
            "GEOMAP_DATA_ROOT": str(data_root),
            "GEOMAP_CACHE_ROOT": str(cache_root),
            "GEOMAP_MODEL_ROOT": str(tmp_path / "models"),
            "GEOMAP_MCP_ALLOWED_ROOTS": f"{data_root}:{cache_root}",
        }
    )

    async def workflow():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(ROOT / "tests/fixtures/mcp_stdio_server.py")],
            env=environment,
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert len(tools.tools) == 8

                registered = await session.call_tool("geomap_register_map", {"path": str(image)})
                assert not registered.isError
                map_id = registered.structuredContent["map_id"]
                source_uri = registered.structuredContent["source_uri"]
                source = await session.read_resource(source_uri)
                assert source.contents[0].blob

                processed = await session.call_tool("geomap_process_image", {"map_id": map_id})
                assert not processed.isError
                artifact_uri = processed.structuredContent["artifacts"][0]["uri"]
                artifact = await session.read_resource(artifact_uri)
                assert artifact.contents[0].blob

                georef = await session.call_tool(
                    "geomap_georeference",
                    {
                        "map_id": map_id,
                        "crs": "EPSG:4326",
                        "gcps": [
                            {"pixel_x": 0, "pixel_y": 0, "world_x": -90, "world_y": 46},
                            {"pixel_x": 100, "pixel_y": 100, "world_x": -89, "world_y": 45},
                        ],
                        "pixel_extent": [0, 0, 100, 100],
                    },
                )
                assert not georef.isError
                assert georef.structuredContent["georef_uri"].startswith("geomap://maps/")

                queried = await session.call_tool("geomap_query_map", {"map_id": map_id})
                assert not queried.isError
                assert queried.structuredContent["total_records_found"] == 1
                bundle_uri = queried.structuredContent["bundle_uri"]

                rendered = await session.call_tool(
                    "geomap_render_knowledge_overlay",
                    {"map_id": map_id, "bundle_uri": bundle_uri},
                )
                assert not rendered.isError
                overlay_uri = rendered.structuredContent["resources"][0]["uri"]
                overlay = await session.read_resource(overlay_uri)
                assert "<svg" in overlay.contents[0].text

    asyncio.run(workflow())
