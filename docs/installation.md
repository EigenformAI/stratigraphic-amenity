# Installation

Stratigraphic Amenity 0.1.0 supports CPython 3.11 (`>=3.11,<3.12`). The MCP server is local
stdio only. Linux is the primary tested platform; the registry uses `fcntl` locking on POSIX
and falls back to unlocked writes where `fcntl` is unavailable.

## Published Package

Create an isolated environment and install only the capabilities needed:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install stratigraphic-amenity
python -c "import stratigraphic_amenity as sa; print(sa.__version__)"
```

| Profile | pip extra | Purpose |
| --- | --- | --- |
| Base | none | Config, lightweight knowledge contracts, SVG rendering, and SDK imports. |
| Asset downloads | `assets` | Google Drive client used for PEACE's published detector archive. |
| MCP | `mcp` | stdio server, JSON Schema validation, Pillow previews. |
| Georeferencing | `geo` | NumPy affine fitting and pyproj CRS conversion. |
| Local knowledge acceleration | `knowledge-local` | pandas CSV and Shapely geometry engines. |
| Network knowledge | `knowledge-network` | HTTP source sync and live providers. |
| Earth Engine | `knowledge-earthengine` | Google Earth Engine client; external authentication required. |
| Semantic knowledge | `knowledge-semantic` | Sentence Transformers and Torch; install the PEACE knowledge asset. |
| Detectors | `detectors` | PEACE-compatible YOLOv10 runtime dependencies; install runtime and weights separately. |

Example combined installation:

```bash
python -m pip install 'stratigraphic-amenity[mcp,geo,knowledge-network]'
```

Do not install `detectors` and `knowledge-semantic` together. Their declared Torch ranges
conflict; use separate environments. Both can share the same data root and downloaded knowledge
assets.

## Source Checkout

```bash
git clone https://github.com/EigenformAI/stratigraphic-amenity.git
cd stratigraphic-amenity
uv sync --group dev --extra mcp --extra geo
uv run python -c "import stratigraphic_amenity as sa; print(sa.__version__)"
uv run pytest
```

`uv sync` is explicit. Entering the directory does not install dependencies.

## Configure Local State

Defaults are independent of the checkout:

- data: `${XDG_DATA_HOME:-~/.local/share}/stratigraphic-amenity`
- cache: `${XDG_CACHE_HOME:-~/.cache}/stratigraphic-amenity`
- models: `<data-root>/assets/models`
- PEACE YOLOv10 runtime: `<data-root>/assets/runtime/ultralytics`
- knowledge assets: `<data-root>/assets/knowledge`
- normalized source mirrors: `<data-root>/knowledge/sources`

For a checkout-local MCP session:

```bash
mkdir -p data .cache
export GEOMAP_DATA_ROOT="$PWD/data"
export GEOMAP_CACHE_ROOT="$PWD/.cache"
export GEOMAP_MCP_ALLOWED_ROOTS="$PWD/data:$PWD/.cache"
uv run --no-sync stratigraphic-amenity-mcp
```

Use `;` instead of `:` as the path-list separator on Windows. Relative environment paths
resolve from the server launch directory. Python does not automatically load `.env`; export
variables in the shell or pass them through the MCP host. See [configuration](configuration.md).

## Asset Policy

Inspect the release manifest without downloading anything:

```bash
uv run stratigraphic-amenity-assets --list
```

The three manifest entries are approved attribution/download paths:

- `peace-yolov10-runtime`: source-sync from pinned PEACE commit, AGPL-3.0;
- `peace-layout-detectors`: download PEACE's published archive, MIT, SHA-256 verified;
- `peace-knowledge-base`: source-sync K2 (MIT), USGS earthquake data (CC0/public domain), and GEM
  active-fault data (CC BY-SA 4.0).

Install all assets into the default XDG data root:

```bash
python -m pip install 'stratigraphic-amenity[assets]'
stratigraphic-amenity-assets --all
```

Use `--root PATH` to select another data root and `--force` to atomically replace an existing
installation. Set `GEOMAP_DATA_ROOT` to that same path when running the SDK or MCP server. The
installer confines destinations to the selected root, extracts only declared archive subtrees,
rejects traversal/symlinks and extraction-size overflow, verifies source-tree and weight-archive
digests, and applies the documented path-hook removal to the PEACE runtime.
See [NOTICE](../NOTICE) and [provenance](provenance.md).

## Optional Knowledge Mirrors

The network extra can create normalized local mirrors for USGS events and GEM active faults.
These commands access third-party services and write data plus a provenance manifest beneath
`GEOMAP_KNOWLEDGE_SOURCES_ROOT`:

```bash
uv run --extra knowledge-network python -m stratigraphic_amenity.knowledge.sources.sync \
  usgs_fdsn_events \
  --profile-json docs/source-manifests/usgs_fdsn_events/default.json

uv run --extra knowledge-network python -m stratigraphic_amenity.knowledge.sources.sync \
  gem_global_active_faults \
  --profile-json docs/source-manifests/gem_global_active_faults/default.json
```

USGS sync can be bounded with all four of `--min-lon`, `--min-lat`, `--max-lon`, and
`--max-lat`. `--version` chooses the mirror directory. Only these two sync adapters are
implemented; other live providers query their services on demand.

## User-Supplied Images

No map is bundled or downloaded. Every map workflow requires an image supplied by the user and
readable by the process. For MCP, place it under a root listed in
`GEOMAP_MCP_ALLOWED_ROOTS`. Supported registration MIME types are PNG, JPEG, TIFF, WebP, and
GIF; the default maximum source size is 200 MiB.

The asset-free georeferencing example accepts an image name for display plus explicit GCPs:

```bash
uv run --extra geo python examples/02_georeference_map.py path/to/map.png \
  --crs EPSG:26915 \
  --gcp 0 0 660000 5400000 \
  --gcp 1000 1000 690000 5370000 \
  --pixel-extent 0 0 1000 1000
```

The operator or client must read the map's CRS and coordinates; OCR and a VLM are not included.

## Clean-Clone Verification

```bash
uv sync --group dev --extra mcp --extra geo
uv run pytest
uv run ruff check .
uv run stratigraphic-amenity-assets --list
uv run python -c "from stratigraphic_amenity.mcp.adapter import GeomapMcpAdapter; print(GeomapMcpAdapter().list_capabilities()['structuredContent']['capabilities'])"
```

Without optional assets, capability output gives the exact installer commands that are missing.
After installing `detectors` plus the runtime and weights, `map_processing.ready` is true. After
installing the PEACE knowledge base, local K2, USGS earthquake, and GEM active-fault providers
become ready as their Python dependencies allow. Provider readiness is not proof that a dataset
covers a query; inspect warnings and provenance.
