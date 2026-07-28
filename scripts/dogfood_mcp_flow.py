#!/usr/bin/env python
"""Dogfood the peace-tool-pool MCP server end-to-end over the real stdio protocol.

Launches ``peace-tool-pool-mcp`` as a subprocess, speaks MCP over stdio, and runs
the recommended HIE -> DKI -> overlay loop against a ``data/test-inputs`` map,
reading back ``geomap://`` resources through ``resources/read``.

This is a *client*: it never imports the adapter directly, so it exercises the
JSON-RPC surface a real VLM agent would see.

Run:  uv run --no-sync python scripts/dogfood_mcp_flow.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import AnyUrl

REPO = Path(__file__).resolve().parent.parent
MAP = "data/test-inputs/7-1-regional-geology-osmani-1993.png"

# Hand-read GCPs for Osmani (EPSG:26915, UTM NAD83 Z15); see memory test-input-georef-gcps.
CRS = "EPSG:26915"
GCPS = [
    {"pixel_x": 167, "pixel_y": 99, "world_x": 660000, "world_y": 5400000},
    {"pixel_x": 1175, "pixel_y": 1238, "world_x": 690000, "world_y": 5360000},
]


def banner(step: str) -> None:
    print(f"\n{'=' * 70}\n{step}\n{'=' * 70}")


def sc(result) -> dict:
    """structuredContent of a CallToolResult, or an {} fallback."""
    return result.structuredContent or {}


async def main() -> int:
    env = dict(os.environ)
    env.setdefault("GEOMAP_DATA_ROOT", str(REPO / "data"))
    env.setdefault("GEOMAP_CACHE_ROOT", str(REPO / ".cache"))
    env["GEOMAP_MCP_ALLOWED_ROOTS"] = os.pathsep.join(
        [str(REPO / "data"), str(REPO / ".cache")]
    )

    params = StdioServerParameters(
        command="uv",
        args=["run", "--no-sync", "peace-tool-pool-mcp"],
        env=env,
        cwd=str(REPO),
    )

    failures: list[str] = []

    def check(cond: bool, msg: str) -> None:
        status = "PASS" if cond else "FAIL"
        print(f"  [{status}] {msg}")
        if not cond:
            failures.append(msg)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # ---- list_tools: the discoverable surface -----------------------
            banner("0. tools/list  (what an agent discovers)")
            tools = (await session.list_tools()).tools
            names = [t.name for t in tools]
            for t in tools:
                ann = t.annotations
                ro = getattr(ann, "readOnlyHint", None) if ann else None
                print(f"  - {t.name:32} readOnly={ro}")
            check(len(names) == 8, f"8 tools advertised (got {len(names)})")

            # ---- list_capabilities ------------------------------------------
            banner("1. geomap_list_capabilities")
            cap = sc(await session.call_tool("geomap_list_capabilities", {}))
            installed = cap.get("installed", {})
            det = cap.get("detectors", {})
            prov = cap.get("providers", [])
            print(f"  installed: {json.dumps(installed)}")
            print(f"  detectors: {json.dumps(det)}")
            print(f"  providers: {[p['id'] for p in prov]}")
            print(f"  default-enabled: {[p['id'] for p in prov if p['default_enabled']]}")
            check(installed.get("mcp") and installed.get("pyproj"), "mcp + pyproj reported installed")
            check(det.get("component_model_present") and det.get("legend_model_present"), "detector weights present")

            # ---- register_map -----------------------------------------------
            banner("2. geomap_register_map  (HIE: make addressable)")
            reg = sc(await session.call_tool("geomap_register_map", {"path": MAP}))
            map_id = reg["map_id"]
            print(f"  map_id={map_id}  map_uri={reg.get('map_uri')}  source_uri={reg.get('source_uri')}")
            check(bool(map_id), "map registered, map_id returned")
            check(bool("source_path" not in json.dumps(reg) or reg.get("source_path_redacted")),
                  "no raw absolute path leaked")

            # ---- process_image (HIE) ----------------------------------------
            banner("3. geomap_process_image  (HIE: layout + legend extraction)")
            proc = sc(await session.call_tool("geomap_process_image", {"map_id": map_id}))
            regions = {k: len(v) for k, v in proc.get("regions", {}).items() if v}
            arts = proc.get("artifacts", [])
            print(f"  text_summary: {proc.get('text_summary')}")
            print(f"  regions: {regions}")
            print(f"  legend entries: {len(proc.get('legend', []))}")
            roles = sorted({a.get('role') for a in arts})
            print(f"  artifact roles: {roles}")
            check(regions.get("main_map", 0) >= 1, "main_map region detected")
            check(len(arts) >= 3, "crops + overlay registered as resources")
            crop_uri = next((a["uri"] for a in arts if a.get("role") == "component_crop"), None)
            overlay_art = next((a["uri"] for a in arts if a.get("role") == "detection_overlay"), None)

            # ---- georeference -----------------------------------------------
            banner("4. geomap_georeference  (HIE -> world bounds from GCPs)")
            geo = sc(await session.call_tool(
                "geomap_georeference",
                {"map_id": map_id, "crs": CRS, "gcps": GCPS},
            ))
            b = geo.get("bounds", {})
            print(f"  text_summary: {geo.get('text_summary')}")
            print(f"  crs={geo.get('crs')}  residual={geo.get('residual')}")
            print(f"  bounds: lon[{b.get('min_lon'):.4f},{b.get('max_lon'):.4f}] "
                  f"lat[{b.get('min_lat'):.4f},{b.get('max_lat'):.4f}]")
            print(f"  georef_uri={geo.get('georef_uri')}")
            # Expected AOI ~ -90.9..-90.4 lon, 48.3..48.8 lat (Shebandowan, NW Ontario)
            in_aoi = (-91.5 < b.get("min_lon", 0) < -90.0) and (48.0 < b.get("max_lat", 0) < 49.5)
            check(in_aoi, "bounds land in expected NW-Ontario AOI")
            check(geo.get("residual", 9e9) < 1.0, f"GCP residual < 1px (got {geo.get('residual')})")

            # ---- query_map (DKI) --------------------------------------------
            banner("5. geomap_query_map  (DKI: knowledge for the map bounds)")
            dki = sc(await session.call_tool(
                "geomap_query_map",
                {
                    "map_id": map_id,
                    "question": "What mineral occurrences, faults and seismicity are in this map?",
                    "include": ["earthquake_history", "active_faults", "mineral_occurrences"],
                },
            ))
            # The adapter now surfaces record yield directly in the envelope, so a
            # client need not re-sum item.value (the old summary said "3 items").
            recs = dki.get("record_counts", {})
            print(f"  text_summary: {dki.get('text_summary')}")
            print(f"  record_counts: {recs}")
            print(f"  total found/returned: {dki.get('total_records_found')}/"
                  f"{dki.get('total_records_returned')}  truncated={dki.get('truncated')}")
            print(f"  warnings: {dki.get('warnings', [])}")
            print(f"  bundle_uri={dki.get('bundle_uri')}")
            bundle_uri = dki.get("bundle_uri")
            check(bundle_uri is not None, "DKI bundle persisted as a resource")
            check(recs.get("mineral_occurrences", 0) > 0,
                  f"mineral_occurrences returned live records (got {recs.get('mineral_occurrences', 0)})")
            check(str(dki.get("total_records_found")) in (dki.get("text_summary") or ""),
                  "text_summary surfaces record yield (not just item count)")
            # On cratonic AOI, seismic/fault providers are expected ~empty (coverage gap).
            print("  NOTE: earthquake/active_faults == 0 is EXPECTED here (cratonic AOI, GEM Canada gap);")
            print("        mineral_occurrences hits OGS Ontario live (federated ArcGIS).")

            # ---- enrich_legend ----------------------------------------------
            banner("6. geomap_enrich_legend  (DKI: one label -> rock type + age)")
            enr = sc(await session.call_tool("geomap_enrich_legend", {"label": "granite"}))
            print(f"  text_summary: {enr.get('text_summary')}")
            print(f"  payload keys: {sorted(k for k in enr if k not in ('trace_id','text_summary'))}")
            check("text_summary" in enr, "legend enrichment returned an envelope")

            # ---- render_knowledge_overlay -----------------------------------
            banner("7. geomap_render_knowledge_overlay  (PEQA: visual evidence)")
            ovl = sc(await session.call_tool(
                "geomap_render_knowledge_overlay",
                {"map_id": map_id, "bundle_uri": bundle_uri},
            ))
            res_list = ovl.get("resources", [])
            print(f"  text_summary: {ovl.get('text_summary')}")
            print(f"  overlay resources: {[r.get('uri') for r in res_list]}")
            print(f"  warnings: {ovl.get('warnings', [])}")
            overlay_uri = res_list[0]["uri"] if res_list else None
            check(overlay_uri is not None, "overlay resource produced")

            # ---- resources/read: prove geomap:// handles resolve ------------
            banner("8. resources/read  (read geomap:// handles back as a client)")
            for label, uri in [("component crop", crop_uri),
                               ("detection overlay", overlay_art),
                               ("knowledge bundle", bundle_uri),
                               ("knowledge overlay", overlay_uri)]:
                if not uri:
                    check(False, f"{label}: no URI to read")
                    continue
                rr = await session.read_resource(AnyUrl(uri))
                c = rr.contents[0]
                blob = getattr(c, "blob", None)
                text = getattr(c, "text", None)
                kind = "blob" if blob else "text"
                size = len(blob) if blob else len(text or "")
                mime = getattr(c, "mimeType", None)
                print(f"  read {label:18} {uri}")
                print(f"       -> {kind} {mime} ({size} chars/bytes)")
                check(size > 0, f"{label} resource resolved with content")

    banner("RESULT")
    if failures:
        print(f"  {len(failures)} FAILURE(S):")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("  ALL CHECKS PASSED — MCP HIE->DKI->overlay loop dogfooded over stdio.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
