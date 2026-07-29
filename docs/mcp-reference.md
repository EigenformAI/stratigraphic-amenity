# MCP Reference

Stratigraphic Amenity 0.1.0 exposes ten tools by default, including two independently
operator-disableable provisioning tools, and resource reads through the local stdio
transport. The server name is `stratigraphic-amenity`; the executable is
`stratigraphic-amenity-mcp`. It does not expose HTTP, prompts, `resources/list`, or resource
templates.

## Common Contract

Every tool input is JSON Schema draft 2020-12 with `additionalProperties: false`. Successful
calls return MCP content plus `structuredContent` containing at least:

```json
{
  "schema_version": "<payload-schema-or-geomap-tool-result/v1>",
  "trace_id": "<hex-id>",
  "text_summary": "<human summary>",
  "warnings": [],
  "resource_links": []
}
```

Tool-specific fields are additive. In 0.1.0, each tool's advertised output schema validates
only the common fields and permits additional properties; generated clients must not assume a
fully typed tool-specific output schema. `resource_links` are also appended as MCP
`resource_link` content. Some image-producing tools include a bounded inline preview.

Errors set MCP `isError: true` and return a project-defined structured envelope:

```json
{
  "schema_version": "geomap-error/v1",
  "isError": true,
  "error": {
    "code": "invalid_arguments",
    "message": "Input validation error: ...",
    "trace_id": "<hex-id>",
    "details": {},
    "recovery_hints": [],
    "cause": {"type": "missing_python_module", "module": "cpuinfo"}
  },
  "code": "invalid_arguments",
  "message": "Input validation error: ...",
  "trace_id": "<hex-id>",
  "text_summary": "Input validation error: ..."
}
```

`details`, `recovery_hints`, and `cause` are omitted when empty. Causes expose only allowlisted
identifiers such as a missing Python module or shared-library basename, never arbitrary exception
text. These fields are a Stratigraphic Amenity
contract, not standard MCP error fields.

## Tools

### `geomap_list_capabilities`

Inputs: none.

Returns schema versions, installed-module probes, detector files/runtime status, capability
readiness, ten provider registrations, redacted allowed-root labels, and byte limits. Each
capability/provider has `registered`, `installed`, `configured`, `ready`, and
`missing_requirements`. Provider records also include `supported_requests`, whose values are
`bounds`, `legend_labels`, or `query_text`. The aggregate `knowledge_query` capability reports
`ready_provider_count` and `registered_provider_count`; its `ready` field means at least one
provider can serve a supported request, not that every provider is ready.

Readiness is a prerequisite signal, not a coverage guarantee. In particular, earthquake and
active-fault provider readiness does not verify that a local mirror file exists. Query and
inspect warnings/provenance before making factual claims.

Annotations: read-only, idempotent.

### `geomap_prepare_detectors`

Inputs: none. This tool is exposed by default and is the supported way to make the detector
ready; an operator may withhold it with `GEOMAP_MCP_ENABLE_DETECTOR_PREPARATION=false`. It
requires the `assets` extra in the server environment, and does not install Python packages, so
the `detectors` extra must already be present for `map_processing` to become ready. It downloads
and installs exactly `peace-yolov10-runtime` and `peace-layout-detectors` from `assets/manifest.toml`
into the standard `GEOMAP_DATA_ROOT` destinations. Callers cannot supply URLs, asset IDs, roots,
or a force flag. Custom model/runtime roots are rejected.

Returns redacted per-asset status, `performs_network_access: true` (a side-effect declaration, not
a connectivity probe), and a fresh `map_processing` readiness report. The operation can
download about 200 MiB and use substantially more disk during extraction. It cannot install Python
or system packages. Annotations: state-changing, non-destructive, idempotent.

### `geomap_prepare_knowledge`

Inputs: none. This tool is exposed by default; an operator may withhold it with
`GEOMAP_MCP_ENABLE_KNOWLEDGE_PREPARATION=false`. It requires the `assets` extra and installs
exactly `peace-knowledge-base` from `assets/manifest.toml` into the standard
`GEOMAP_DATA_ROOT/assets/knowledge` destination. Callers cannot supply URLs, asset IDs, roots, or
a force flag. Custom knowledge paths are rejected.

Returns redacted per-asset status, `performs_network_access: true`, and fresh readiness for every
registered provider. Its text result names ready and still-unavailable providers and recommends
retrying earlier requests to providers that are now ready. Installing the asset does not install optional Python packages, configure
credentials, sync source mirrors, or guarantee source coverage. Annotations: state-changing,
non-destructive, idempotent.

### `geomap_register_map`

Required input:

```json
{"path":"./data/map.png"}
```

`path` may also be an existing `geomap://maps/<map-id>` URI, although the schema names the field
`path`. Files are canonicalized, including symlinks, then checked against allowed roots, media
types, and the 200 MiB source limit. Supported image MIME types are PNG, JPEG, TIFF, WebP, and
GIF.

Returns `map_id`, `map_uri`, `source_uri`, `mime_type`, and `source_path_redacted`. Registering
the same canonical path reuses its map ID. Persists registry state.

Annotations: state-changing, idempotent because registering the same canonical path reuses its
map ID.

### `geomap_process_image`

Exactly one input is required:

```json
{"map_id":"<map-id>"}
```

or

```json
{"map_uri":"geomap://maps/<map-id>"}
```

Requires `capabilities.map_processing.ready`. It detects component regions and legend units,
writes crops, corner crops, a detection overlay, and metadata, then persists redacted processing
state and artifact URIs. Returns `map-processing/v1` fields including image size, regions,
legend entries, artifacts, `warnings`, and optional preview.

Every box in `regions` and `legend` is in the full-resolution source frame, declared by the
payload's `coordinate_frame: "source"`. An inlined preview is downsampled to fit the response
budget and declares `coordinate_frame: "preview"` in its own metadata alongside `source_width`,
`source_height`, `width`, and `height`. Never read coordinates off the preview image; the two
frames differ, often by more than 1.5x.

Legend `label` is `null` unless text was actually transcribed, and every entry carries
`label_extraction`, either `"extracted"` or `"not_available"`. This build ships no OCR, so
`not_available` is the normal case and a payload-level warning says so. Do not infer a label from
the preview or the source image; obtain it from the user or a separate OCR/VLM system.

Readiness requires successful subprocess imports of the `detectors` extra plus the managed
`peace-yolov10-runtime` and `peace-layout-detectors` assets. When the detector is not ready the
error envelope carries the complete outstanding list in `details.missing_requirements`, the
underlying detector message in `details.detector_error`, and `recovery_hints` naming the remedy
that works from an MCP client: `geomap_prepare_detectors` when it is exposed, otherwise
escalation to the operator. Manual commands use `--root "$GEOMAP_DATA_ROOT"` and must run in the
server environment; absolute server paths remain redacted.

Annotations: state-changing, non-idempotent because processing rewrites cached map state.

### `geomap_georeference`

Required fields: `crs` and at least two `gcps`. `crs` is an EPSG integer/string or supported UTM
text. Each GCP requires `pixel_x`, `pixel_y`, `world_x`, and `world_y` numbers.

Optional fields: `map_id` or `map_uri` (not both), four-number `pixel_extent`, and
`main_map_artifact_uri`. Pixel extent is resolved in this order: explicit extent, named
artifact bbox, stored main-map detection. If none is available, the call fails.

Two GCPs fit an axis-aligned transform and must differ in both pixel axes. Three or more
non-collinear GCPs fit a least-squares affine. Returns `georef/v1` with canonical CRS, six affine
coefficients, EPSG:4326 bounds, residual, extent, GCPs, and count. With a map reference, writes
`geomap://maps/<map-id>/georef.json` and updates registry state.

Annotations: state-changing, non-idempotent because georeference state is rewritten.

### `geomap_query_knowledge`

At least one of `bounds`, `legend_labels`, or `query_text` must be present. `bounds` is an
EPSG:4326 object with ordered longitude/latitude values. Optional controls:

- `include`, `exclude`: provider ID, name, or output-key filters;
- `max_records`: global non-negative record limit;
- `max_records_by_provider`: per-provider non-negative limits;
- `provider_options`: provider-keyed option objects.

Returns a `knowledge/v2` bundle plus `bundle_uri`, `record_counts`,
`total_records_found`, `total_records_returned`, and `truncated`. Each item contains provider,
value, summary, source, `record_count`, truncation, and provenance. Writes provider cache entries
when enabled and always writes a new bundle resource.
The primary text summary repeats every bundle warning after path redaction so text-only MCP hosts
do not turn warning evidence into a count. Successful partial queries add an environment-aware
preparation or operator remedy for unavailable providers. Broad queries also identify compatible
providers not consulted because `default_enabled` is false and show how to opt in with `include`.

Annotations: state-changing, non-idempotent.

### `geomap_query_map`

Accepts `map_id` or `map_uri` (not both), inline `metadata`, and all knowledge-query controls.
At least one of a map reference, metadata, explicit bounds, or legend labels must be present.
`question` is used as query text unless `query_text` is supplied.

Resolution order is explicit arguments, inline metadata, stored processing legend, then stored
georef bounds. Semantic execution requires bounds or at least one label; otherwise
`georef_required` is returned. Output and side effects match `geomap_query_knowledge`; a map ID
associates the bundle with map state.

Annotations: state-changing, non-idempotent.

### `geomap_enrich_legend`

Required input: non-empty `label` string. Queries exactly `rock_type` and `rock_age`, returning
`label`, nullable `lithology`, nullable `stratigraphic_age`, provider items, and warnings.

The required rock-type and rock-age files are installed by the `peace-knowledge-base` asset. The
tool remains registered but should be called only when both providers report ready.

Annotations: read-only, idempotent.

### `geomap_render_knowledge_overlay`

Requires exactly one of `bundle_uri` or inline `bundle`, plus at least one of a map reference or
inline `georef`. `map_id` and `map_uri` are mutually exclusive. Inline georef requires `crs`,
`affine`, `bounds`, and `residual`.

Writes a standalone SVG beneath the cache root and registers it. With a map reference, it also
attempts a map-annotated PNG. PNG failure is returned as a warning without discarding the SVG.
Returns overlay items, hidden out-of-bounds annotations, warnings, resources, and optional PNG
preview. Every call mints new overlay IDs and files.

Annotations: state-changing, non-idempotent.

## Resource URIs

| URI | Content | Created/read behavior |
| --- | --- | --- |
| `geomap://maps/<id>` | Redacted map registration JSON | Registration creates state; reading writes a current `map.json` snapshot. |
| `geomap://maps/<id>/source` | Original map image | Registered by `geomap_register_map`; complete image bytes may be read. |
| `geomap://maps/<id>/georef.json` | `georef/v1` JSON | Written by map-backed georeferencing. |
| `geomap://artifacts/<id>.<ext>` | Crop or detector overlay | Written and registered by processing. |
| `geomap://bundles/<id>.json` | Knowledge bundle snapshot | Written for every knowledge query. |
| `geomap://overlays/<id>.<ext>` | SVG or PNG overlay | Written for every render call. |

Clients discover URIs only from tool results and must retain them. Resource reads return text
for JSON, SVG, and text files; other files are returned as bytes by the MCP SDK. Unknown,
stale, escaped, or oversized backing files fail. The default resource-read limit is 50 MiB.

## Persistence And Paths

Default state:

```text
<cache-root>/mcp/v1/registry.json
<cache-root>/mcp/v1/maps/<map-id>/georef.json
<cache-root>/mcp/v1/bundles/<bundle-id>.json
<cache-root>/mcp/v1/overlays/<trace-id>.svg|png
<cache-root>/knowledge/v2/providers/<provider-id>/<cache-key>.json
<cache-root>/<dataset-source>/map_processing/...
```

Registry writes are atomic and merge concurrent state under a POSIX file lock. A corrupt
registry fails closed with `registry_corrupt` rather than silently discarding state. Back up and
remove the registry under the configured cache root before re-registering maps; backing files
are not rediscovered. Deleting or changing cache roots invalidates retained URIs. There is no MCP
cleanup or retention tool.

## Error Codes

| Code | Meaning |
| --- | --- |
| `invalid_arguments` | Input failed advertised JSON Schema. |
| `unknown_tool` | Tool name is not registered. |
| `disallowed_path` | File resolves outside allowed roots or is not an allowed regular file. |
| `artifact_not_found` | File, map ID, URI, georef, or backing resource is absent/stale. |
| `unsupported_media` | Unsupported source image or non-JSON bundle resource. |
| `oversize_image` | Source or resource exceeds its byte limit. |
| `registry_corrupt` | Persistent registry JSON is invalid and must be backed up/removed before restart. |
| `missing_extra` | Optional dependency/runtime/model requirement is unavailable. |
| `invalid_bounds` | Bounds, CRS, GCPs, affine fit, or pixel extent is invalid. |
| `georef_required` | Stored/inline bounds, labels, or georef prerequisite is missing. |
| `unknown_provider` | Provider filter/options resolution failed or a selected provider raised a provider-level failure. |
| `invalid_output` | Adapter result failed the advertised output schema. |
| `internal_error` | Unexpected server exception; traceback goes to stderr. |

Resource-read errors originate from the same registry checks but are surfaced through the MCP
resource request rather than a tool result envelope.

## Transport And Trust

The server reserves stdout for stdio JSON-RPC and writes redacted startup/tool timing diagnostics
and unexpected tracebacks to stderr. `GEOMAP_LOG_LEVEL` controls the threshold. It has
the filesystem and ambient credentials of its process. Allowed roots are accidental-access
controls, not a sandbox; canonicalization rejects symlink escapes but cannot replace OS process
isolation. Model-visible tool payloads redact recognized absolute path fields, while resource
reads intentionally return file contents. Live provider requests disclose query bounds and
filters to third parties.
