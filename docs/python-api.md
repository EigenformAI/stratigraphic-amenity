# Python API

The supported public package is `stratigraphic_amenity`. Top-level stable exports are
`Bounds`, `KnowledgeConfig`, `KnowledgeService`, `MapProcessingConfig`,
`MapProcessingService`, and `__version__`. More specialized contracts are exported from the
documented subpackages below.

## Paths And Configuration

`MapProcessingConfig.from_env(base_dir=None)` and `KnowledgeConfig.from_env(base_dir=None)` load
`GEOMAP_*` values. Absolute paths remain absolute; relative paths resolve against `base_dir` or
the process launch directory. Defaults use XDG data/cache roots. Python does not load `.env`.

```python
from stratigraphic_amenity import KnowledgeConfig, MapProcessingConfig

knowledge = KnowledgeConfig.from_env()
processing = MapProcessingConfig.from_env()
```

Constructors accept dataclass values directly for tests or explicit applications. Both services
write caches by default; set `write_cache=False` on a constructed config to disable service
cache writes. MCP registry/bundle persistence is separate and always enabled.

## Georeferencing

Install the `geo` extra. Public exports from `stratigraphic_amenity.georef` are:

- `resolve_crs(spec)`;
- `GroundControlPoint`;
- `AffineTransform`;
- `GeoReference`;
- `fit_affine(gcps)`;
- `georeference_bounds(crs=, gcps=, pixel_extent=)`;
- `GeoReferenceError`, `CRSResolutionError`, and `AffineFitError`.

```python
from stratigraphic_amenity.georef import GroundControlPoint, georeference_bounds

ref = georeference_bounds(
    crs="UTM N83 Zone 15",
    gcps=[
        GroundControlPoint(0, 0, 660000, 5400000),
        GroundControlPoint(1000, 1000, 690000, 5370000),
    ],
    pixel_extent=(0, 0, 1000, 1000),
)
lon, lat = ref.pixel_to_lonlat(500, 500)
pixel_x, pixel_y = ref.lonlat_to_pixel(lon, lat)
```

`resolve_crs` accepts an integer, `EPSG:<code>`, or common NAD27/NAD83/WGS84 UTM text. Bare UTM
defaults to WGS84. Two GCPs fit an axis-aligned transform; three or more non-collinear points
fit a general affine. `GeoReference.residual` is RMS error in world/map CRS units;
`residual_m` is geodesic RMS error in metres. Use four or more GCPs for a diagnostic residual and
`holdout_error`; exact two- and three-point fits have no independent error check.
Returned bounds are always EPSG:4326.

## Knowledge Service

Public exports from `stratigraphic_amenity.knowledge` include `Bounds`, `KnowledgeConfig`,
`KnowledgeService`, `KnowledgeRequest`, `KnowledgeBundle`, `KnowledgeItem`,
`LegendEnrichment`, and overlay contracts/renderers.

### Explicit Bounds

```python
from stratigraphic_amenity.knowledge import Bounds, KnowledgeService

service = KnowledgeService.from_env()
bundle = service.query_bounds(
    Bounds(min_lon=-122.5, min_lat=37.0, max_lon=-121.5, max_lat=38.0),
    include=("earthquake_history", "active_faults"),
    max_records=20,
)

for warning in bundle.warnings:
    print("warning:", warning)
for item in bundle.items:
    print(item.provider, item.record_count, item.provenance)
```

`Bounds` accepts only EPSG:4326 (or the normalized alias `OGC:CRS84`) and requires longitude
within `[-180,180]`, latitude within `[-90,90]`, and ordered coordinates.

`query_bounds` takes `include`, `exclude`, `max_records`, and `provider_options`. For
provider-specific limits and query text/labels, use `query(KnowledgeRequest(...))`:

```python
from stratigraphic_amenity.knowledge import Bounds, KnowledgeRequest, KnowledgeService

request = KnowledgeRequest(
    bounds=Bounds(-80.2, 46.1, -79.8, 46.4),
    include=("mineral_occurrences",),
    max_records_by_provider={"mineral_occurrences": 25},
    provider_options={"mineral_occurrences": {"sources": ["ontario_mineral_deposit_inventory"]}},
)
bundle = KnowledgeService.from_env().query(request)
```

This explicit mineral request accesses the network. See [providers](providers.md).

### Antimeridian Extents

`query_extent(min_lon=, min_lat=, max_lon=, max_lat=, ...)` splits a wrapping extent into two
non-wrapping `Bounds` parts. Providers that cannot handle split extents fail. Direct `Bounds`
does not permit `min_lon > max_lon`.

### Map Metadata

`query_map(metadata, question=None, ...)` extracts bounds from `metadata["bounds"]` or computes
them from `metadata["georef"]`. Labels come from `legend_labels` or legend `label`/`text` fields.
At least bounds or a label is required.

```python
bundle = service.query_map(
    {
        "bounds": {"min_lon": -80.2, "min_lat": 46.1, "max_lon": -79.8, "max_lat": 46.4},
        "legend_labels": ["sandstone"],
    },
    question="Relevant geological context",
    include=("earthquake_history",),
)
```

### Legend Enrichment

`enrich_legend_label(label)` queries `rock_type` and `rock_age`. Install their K2 files with
`stratigraphic-amenity-assets peace-knowledge-base` before calling this entry point.

## Knowledge Rendering

`extract_knowledge_overlay(bundle, metadata=None)` converts provider records and query/provenance
bounds into renderable items. `render_knowledge_overlay_svg(overlay, output_path)` is lightweight.
`render_knowledge_overlay_on_image(...)` imports the image-processing stack lazily.

```python
from stratigraphic_amenity.knowledge import extract_knowledge_overlay, render_knowledge_overlay_svg

overlay = extract_knowledge_overlay(bundle)
render_knowledge_overlay_svg(overlay, "knowledge-overlay.svg")
```

Provider points outside query bounds are omitted and recorded in `overlay.out_of_bounds` and
`overlay.warnings`. Rendering writes the requested path and creates parent directories.

## Map Processing

`MapProcessingService.process_image(image_path)` returns `MapProcessingResult` and normally
writes component crops, legend crops, longitude/latitude corner crops, a detection overlay, and
metadata beneath `<cache-root>/<dataset-source>/map_processing/`.

The default service constructs PEACE-derived YOLOv10 component and legend detector adapters.
Install `stratigraphic-amenity[detectors]`, `peace-yolov10-runtime`, and
`peace-layout-detectors` first. The service constructor also accepts injected
`component_detector` and `legend_detector` objects for testing or alternative implementations.

Public map-processing contracts include `ArtifactRef`, `Detection`, `ImageSize`, `LegendEntry`,
`MapProcessingResult`, `MapProcessingConfig`, and `MAP_PROCESSING_RESULT_SCHEMA`.

## MCP Embedding

Applications can construct `stratigraphic_amenity.mcp.adapter.GeomapMcpAdapter` or call
`stratigraphic_amenity.mcp.server.create_server(adapter=None)`. The latter requires the `mcp`
extra. The adapter is protocol-independent but persists the same registry/resources as the
stdio server. MCP tool schemas, redaction, and error envelopes are documented in
[MCP reference](mcp-reference.md).
