# Configuration

Configuration is read from process environment variables by `MapProcessingConfig`,
`KnowledgeConfig`, and the MCP `ResourceRegistry`. Python does not load `.env`. Pass variables
through the shell, service manager, or MCP host. Relative path values resolve from the process
launch directory (or an explicit SDK `base_dir`); paths are expanded and canonicalized.

The `geomap` prefix is retained domain protocol vocabulary. It does not identify a separate
product.

## Root And MCP Variables

| Variable | Default | Owner | Secret | Meaning |
| --- | --- | --- | --- | --- |
| `XDG_DATA_HOME` | `~/.local/share` | shared paths | no | Base for default data root. |
| `XDG_CACHE_HOME` | `~/.cache` | shared paths | no | Base for default cache root. |
| `GEOMAP_DATA_ROOT` | `<XDG data>/stratigraphic-amenity` | all services | no | User maps and default asset/source roots. |
| `GEOMAP_CACHE_ROOT` | `<XDG cache>/stratigraphic-amenity` | all services/MCP | sensitive path | Derived artifacts, provider cache, registry, bundles, and overlays. |
| `GEOMAP_MCP_ALLOWED_ROOTS` | data root plus cache root | MCP | sensitive path | OS-path-separator list of roots MCP may register/read. |
| `GEOMAP_MCP_ENABLE_DETECTOR_PREPARATION` | `true` | MCP | no | Expose the detector asset download/install tool. Set to `false` to withhold it; any unrecognized value also withholds it. |
| `GEOMAP_LOG_LEVEL` | `INFO` | MCP | no | Stderr threshold: `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. |
| `GEOMAP_DATASET_SOURCE` | `usgs` | map processing | no | Provenance label and map-processing cache namespace segment. |
| `GEOMAP_MODEL_ROOT` | `<data-root>/assets/models` | map processing | sensitive path | Parent of expected detector model directories. |
| `GEOMAP_ULTRALYTICS_ROOT` | `<data-root>/assets/runtime/ultralytics` | map processing | sensitive path | Managed PEACE YOLOv10 source-sync directory. |
| `GEOMAP_KNOWLEDGE_ROOT` | `<data-root>/assets/knowledge` | knowledge | sensitive path | Parent of installed PEACE K2, USGS, and GEM assets. |
| `GEOMAP_KNOWLEDGE_SOURCES_ROOT` | `<data-root>/knowledge/sources` | knowledge/sync | sensitive path | Versioned normalized source mirrors and manifests. |

`GEOMAP_MCP_ALLOWED_ROOTS` uses `os.pathsep`: `:` on POSIX and `;` on Windows. Empty/unset falls
back to the resolved data and cache roots. Allowed roots are not a sandbox; restrict process OS
permissions independently. The server does not expose their paths, only labels such as
`root_1`.

Expected detector files are `<model-root>/det_component/weights/best.pt` and
`<model-root>/det_legend/weights/best.pt`. Install them with `peace-layout-detectors`; install the
runtime with `peace-yolov10-runtime`.

The asset installer selects its root in this order: explicit `--root`, `GEOMAP_DATA_ROOT`, then
the XDG default. A single installer root can provision detectors only when model and runtime paths
use the standard destinations beneath that data root. Detector preparation is absent from MCP by
default. Enabling it authorizes manifest-pinned network downloads and substantial disk writes; it
does not authorize package-manager commands, arbitrary URLs, caller-selected paths, or `--force`.

## Local Knowledge Files And Sources

| Variable | Default | Secret | Meaning |
| --- | --- | --- | --- |
| `GEOMAP_EARTHQUAKE_CSV` | `<knowledge-root>/earthquake_1970_4.5mag.csv` | sensitive path | Explicit legacy earthquake CSV. |
| `GEOMAP_ACTIVE_FAULT_GEOJSON` | `<knowledge-root>/gem_active_faults_harmonized.geojson` | sensitive path | Explicit legacy active-fault GeoJSON. |
| `GEOMAP_EARTHQUAKE_SOURCE_ID` | `usgs_fdsn_events` | no | Primary earthquake source. |
| `GEOMAP_EARTHQUAKE_SOURCE_IDS` | primary plus `emsc_fdsn_events` when primary is USGS | no | Comma-separated configured earthquake sources. |
| `GEOMAP_ACTIVE_FAULT_SOURCE_ID` | `gem_global_active_faults` | no | Primary active-fault source. |
| `GEOMAP_ACTIVE_FAULT_SOURCE_IDS` | primary plus `diss_seismogenic_sources` when primary is GEM | no | Comma-separated configured fault sources. |
| `GEOMAP_MINERAL_OCCURRENCE_SOURCE_ID` | `ontario_mineral_deposit_inventory` | no | Primary mineral source/fallback. |
| `GEOMAP_MINERAL_OCCURRENCE_SOURCE_IDS` | primary plus `sigeom_mineral_occurrences` when primary is Ontario | no | Comma-separated configured mineral sources. |
| `GEOMAP_GEM_ACTIVE_FAULT_VERSION` | latest available | no | Preferred local GEM mirror directory/version. |
| `GEOMAP_KNOWLEDGE_EARTHQUAKE_ENGINE` | `auto` | no | `auto`, `csv`, or `pandas`; unsupported values fail at query time. |
| `GEOMAP_KNOWLEDGE_FAULT_GEOMETRY_ENGINE` | `auto` | no | `auto`, `bbox`, or `shapely`; unsupported values fail at query time. |

With `auto`, pandas/Shapely are used when installed and standard CSV/bbox logic otherwise. Set
an explicit accelerated engine to require the `knowledge-local` extra.

## Earth Engine

| Variable | Default | Secret | Meaning |
| --- | --- | --- | --- |
| `GEOMAP_EARTHENGINE_PROJECT` | unset | no | Google Cloud/Earth Engine project ID; required for readiness. |
| `GEOMAP_EARTHENGINE_LANDCOVER_DATASET` | `ESA/WorldCover/v200` | no | Earth Engine landcover collection ID. |
| `GEOMAP_EARTHENGINE_POPULATION_DATASET` | `WorldPop/GP/100m/pop` | no | Earth Engine population collection ID. |
| `GEOMAP_EARTHENGINE_SCALE` | `100` | no | Reduction scale in metres. Parsed as integer. |
| `GEOMAP_EARTHENGINE_MAX_PIXELS` | `100000000` | no | Maximum pixels supplied to reductions. Parsed as integer. |

Credentials are not read from a project-specific environment variable. The Earth Engine client
uses its normal ambient authentication. Credential files/tokens are secrets and must not be
committed or passed to a model.

## K2 Paths

| Variable | Default beneath knowledge root | Secret | Provider |
| --- | --- | --- | --- |
| `GEOMAP_K2_ROCK_TYPE_JSON` | `k2_rock_type.json` | sensitive path | `rock_type` |
| `GEOMAP_K2_ROCK_AGE_JSON` | `k2_rock_age.json` | sensitive path | `rock_age` |
| `GEOMAP_K2_ROCK_DETAIL_JSON` | `k2_rock_detail.json` | sensitive path | `rock_knowledge` |
| `GEOMAP_K2_USAGE_JSON` | `k2_usage.json` | sensitive path | `component_usage_knowledge` |
| `GEOMAP_K2_EXPERTISE_JSON` | `k2_expertise.json` | sensitive path | `downstream_task_knowledge` |

The default files are installed together by `stratigraphic-amenity-assets peace-knowledge-base`.

## Semantic Retrieval

| Variable | Default | Secret | Meaning |
| --- | --- | --- | --- |
| `GEOMAP_SEMANTIC_MODEL` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | no | Sentence Transformer model name or local path. |
| `GEOMAP_SEMANTIC_MODEL_REVISION` | unset | no | Optional exact model revision. |
| `GEOMAP_SEMANTIC_DEVICE` | `auto` | no | `auto`, `cpu`, `cuda`, or `cuda:<index>`. |
| `GEOMAP_SEMANTIC_TOP_K` | `5` | no | Default result count. Parsed as integer. |
| `GEOMAP_SEMANTIC_MIN_SCORE` | unset | no | Optional floating-point similarity threshold. |
| `GEOMAP_SEMANTIC_BATCH_SIZE` | `32` | no | Embedding batch size. Parsed as integer. |
| `GEOMAP_SEMANTIC_LOCAL_FILES_ONLY` | `false` | no | Boolean; prohibit model network download when true. |

Accepted true values are `1`, `true`, `yes`, `y`, and `on` (case-insensitive); all other
non-empty values are false. `auto` selects CUDA when Torch reports it available, otherwise CPU.
Explicit CUDA fails if unavailable. Model loading sets `trust_remote_code=False`. Without
`GEOMAP_SEMANTIC_LOCAL_FILES_ONLY`, the model library may access its configured model host on
first use.

## Side Effects And Retention

| Component | Writes |
| --- | --- |
| Map processing | `<cache-root>/<dataset-source>/map_processing/{det,meta,vis}`. |
| Knowledge service | `<cache-root>/knowledge/v2/providers/...` when `write_cache=True`. |
| MCP registry | `<cache-root>/mcp/v1/registry.json` and lock file. |
| MCP map snapshot | `<cache-root>/mcp/v1/maps/<map-id>/map.json`, refreshed when the bare map URI is read. |
| MCP georeference | `<cache-root>/mcp/v1/maps/<map-id>/georef.json`. |
| MCP knowledge | `<cache-root>/mcp/v1/bundles/<bundle-id>.json`. |
| MCP overlay | `<cache-root>/mcp/v1/overlays/<id>.svg` and optional PNG. |
| Source sync | `<knowledge-sources-root>/<source-id>/<version>/...`. |

There are no environment variables for MCP byte limits, registry path, cache retention, or
transport. The implemented defaults are 200 MiB per registered source and 50 MiB per
resource read. SDK constructors can override registry limits/paths and service `write_cache`,
but the CLI does not expose those overrides.

## Example Host Environment

```json
{
  "GEOMAP_DATA_ROOT": "./data",
  "GEOMAP_CACHE_ROOT": "./.cache",
  "GEOMAP_MCP_ALLOWED_ROOTS": "./data:./.cache",
  "GEOMAP_DATASET_SOURCE": "user-supplied",
  "GEOMAP_SEMANTIC_LOCAL_FILES_ONLY": "true"
}
```

Client environment blocks and relative working directories are host conventions. Verify the
resolved setup with `geomap_list_capabilities` without exposing absolute paths to the model.
