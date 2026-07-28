# Stratigraphic Amenity

Stratigraphic Amenity is a Python 3.11 SDK and local Model Context Protocol (MCP) server for
composable geologic-map operations: map registration, affine georeferencing, geological
knowledge retrieval, and evidence rendering. It exposes evidence-producing primitives so a
client can choose its own OCR, vision-language model (VLM), and answer-building policy.

The project builds on the HIE, DKI, and PEQA workflow introduced by
[Microsoft PEACE](https://github.com/microsoft/PEACE) and its
[GeoMap-Agent paper](https://arxiv.org/abs/2501.06184), but is independent and is not affiliated
with or endorsed by Microsoft. Stratigraphic Amenity separates those ideas into Python and MCP
operations, adds opaque persistent resources, affine georeferencing, configurable knowledge
providers, and map-backed overlays. The retained `geomap_*`, `geomap://`, and `GEOMAP_*` names
are domain protocol identifiers, not another product identity.

## Release Status

Version 0.1.0 provides:

- local map registration with allowed-root and size checks;
- affine georeferencing from client-supplied ground control points (GCPs);
- local-mirror and explicit live knowledge-provider interfaces;
- structured warnings, counts, provenance, and persistent knowledge bundles;
- standalone SVG and optional map-annotated PNG overlays;
- nine MCP tools, including detector provisioning, and resource reads over local stdio.

Version 0.1.0 does **not** bundle a map or optional PEACE assets in the Python distributions.
The attributed asset installer source-syncs the PEACE YOLOv10 runtime and knowledge base from a
pinned MIT repository revision and downloads the published detector weights from PEACE's source.
Selected source trees and the weight archive are SHA-256 verified. The Ultralytics runtime remains AGPL-3.0, USGS data
is CC0/public domain, and GEM data is CC BY-SA 4.0. The package does not include OCR, a VLM,
automatic GCP extraction, remote MCP transport, or final PEQA answer generation.

Enable HIE from the current supported source checkout:

```bash
uv sync --group dev --extra mcp --extra assets --extra detectors
uv run --no-sync stratigraphic-amenity-assets peace-yolov10-runtime
uv run --no-sync stratigraphic-amenity-assets peace-layout-detectors
uv run --no-sync stratigraphic-amenity-assets --list
```

The `detectors` and `knowledge-semantic` extras require separate environments because their Torch
ranges conflict. Both environments may use the same XDG data root and installed knowledge files.

## Five-Minute Python Start

Install the source checkout and georeferencing extra:

```bash
git clone https://github.com/EigenformAI/stratigraphic-amenity.git
cd stratigraphic-amenity
uv sync --group dev --extra geo
uv run --no-sync python -c "import stratigraphic_amenity as sa; print(sa.__version__)"
```

Georeference coordinates read from your own map image:

```python
from stratigraphic_amenity.georef import GroundControlPoint, georeference_bounds

result = georeference_bounds(
    crs="EPSG:26915",
    gcps=[
        GroundControlPoint(0, 0, 660000, 5400000),
        GroundControlPoint(1000, 1000, 690000, 5370000),
    ],
    pixel_extent=(0, 0, 1000, 1000),
)
print(result.bounds.to_dict())
print(result.residual)
```

Two GCPs fit an axis-aligned transform and must differ in both pixel axes. Use three or more
non-collinear GCPs for a general least-squares affine fit, and inspect the residual in map CRS
units.

## Five-Minute MCP Start

```bash
uv sync --group dev --extra mcp --extra geo --extra assets --extra detectors
export GEOMAP_DATA_ROOT="$PWD/data"
export GEOMAP_CACHE_ROOT="$PWD/.cache"
export GEOMAP_MCP_ALLOWED_ROOTS="$PWD/data:$PWD/.cache"
uv run --no-sync stratigraphic-amenity-mcp
```

`detectors` and `assets` are included by default because layout detection is the main reason to
run this server, and they cannot be added later from the client's shell. Together they add about
900 MB of CPU-only wheels. Drop `--extra detectors --extra assets` for a georeference- and
knowledge-only server, and drop them if you need `knowledge-semantic`, whose Torch range
conflicts. On first use, call `geomap_prepare_detectors` to fetch the runtime and weights.

The executable speaks JSON-RPC over stdio only; launch it from an MCP host rather than typing
requests into its terminal. A generic host entry after installation is:

```json
{
  "mcpServers": {
    "stratigraphic-amenity": {
      "command": "stratigraphic-amenity-mcp",
      "args": [],
      "env": {
        "GEOMAP_DATA_ROOT": "./data",
        "GEOMAP_CACHE_ROOT": "./.cache",
        "GEOMAP_MCP_ALLOWED_ROOTS": "./data:./.cache"
      }
    }
  }
}
```

Relative paths are resolved from the server launch directory. Client configuration shape,
working-directory behavior, and environment interpolation are host conventions, not MCP
features. Call `geomap_list_capabilities` first. A user-supplied image must already be visible
to the server and inside an allowed root before `geomap_register_map` can accept it.

`geomap_prepare_detectors` is exposed by default, because acquiring the PEACE runtime and weights
is a required step for most of what this package does and the client's shell is not the server's
environment. It installs only the two manifest-pinned, digest-verified detector assets into
`GEOMAP_DATA_ROOT`, and accepts no URLs, asset IDs, roots, or force flag. Clients should obtain
user confirmation before invoking its network downloads and disk writes. Operators who need to
withhold it can set `GEOMAP_MCP_ENABLE_DETECTOR_PREPARATION=false`.

## Workflow

```text
discover capabilities
  -> register a user-supplied map
  -> client reads labels/CRS/GCPs (OCR or VLM, not included)
  -> georeference
  -> query configured knowledge providers
  -> inspect warnings, counts, and provenance
  -> optionally render/read an overlay
  -> client constructs the final answer
```

Knowledge-only queries can start from explicit EPSG:4326 bounds and do not require a map or
detector. Georeference-only work does not require knowledge providers.

## Documentation

- [Installation](docs/installation.md)
- [Configuration](docs/configuration.md)
- [Agent guide](docs/agent-guide.md)
- [MCP reference](docs/mcp-reference.md)
- [Python API](docs/python-api.md)
- [Knowledge providers](docs/providers.md)
- [Provenance and third-party boundaries](docs/provenance.md)
- [Repository guide for coding agents](AGENTS.md)

## License And Citation

Stratigraphic Amenity project code is released under the MIT License. Optional upstream code,
models, and data retain their own terms and attribution. See [NOTICE](NOTICE) and
[provenance](docs/provenance.md). Cite PEACE separately when relying on its concepts or adapted implementation lineage;
the paper is [Empowering Geologic Map Holistic Understanding with MLLMs](https://arxiv.org/abs/2501.06184).
