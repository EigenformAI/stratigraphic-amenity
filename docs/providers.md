# Knowledge Providers

`KnowledgeService` registers ten providers lazily. Registration means a provider is known; it
does not mean dependencies, assets, credentials, network access, or geographic coverage are
available. Call `geomap_list_capabilities`, then inspect every query's warnings and provenance.

## Provider Matrix

| Provider ID | Inputs | Default | 0.1.0 readiness and behavior |
| --- | --- | --- | --- |
| `rock_type` | legend labels | enabled | Ready after `peace-knowledge-base` installs K2 rock-type JSON. |
| `rock_age` | legend labels | enabled | Ready after `peace-knowledge-base` installs K2 rock-age JSON. |
| `earthquake_history` | bounds | enabled | Registered/readiness-reported; needs a local mirror/CSV for offline use or explicit live mode. |
| `active_faults` | bounds | enabled | Registered/readiness-reported; needs a local mirror/GeoJSON for offline use. |
| `mineral_occurrences` | bounds | explicit-only | Live HTTP; needs `knowledge-network`; regional Ontario/Quebec coverage. |
| `landcover_distribution` | bounds | explicit-only | Live Earth Engine; needs `knowledge-earthengine`, project, and external authentication. |
| `population_density` | bounds | explicit-only | Live Earth Engine; needs `knowledge-earthengine`, project, and external authentication. |
| `rock_knowledge` | query text | explicit-only | Needs `peace-knowledge-base` and `knowledge-semantic`. |
| `component_usage_knowledge` | query text | explicit-only | Needs `peace-knowledge-base` and `knowledge-semantic`. |
| `downstream_task_knowledge` | query text | explicit-only | Needs `peace-knowledge-base` and `knowledge-semantic`. |

The capability probe checks K2 path presence, Earth Engine package/project, and mineral HTTP
dependency. It does not currently open earthquake/fault mirror files or test external services,
credentials, semantic model availability, or source coverage. Treat `ready` as necessary but
not sufficient.

## Selection

Without `include`, compatible `default_enabled` providers are selected. `include` and `exclude`
accept normalized provider IDs, provider names, or output keys. Unknown or ambiguous filters
produce warnings; an explicit include with no usable matches fails.

```python
bundle = service.query_bounds(
    bounds,
    include=("earthquake_history", "active_faults"),
    exclude=(),
    max_records=50,
)
```

`max_records` applies to each provider unless overridden by
`max_records_by_provider`. The service default is 50 records per provider. `record_count` is
the number found before truncation; the length of `value` is the number returned.

## Local Mirrors And Source Modes

Normalized mirrors live under:

```text
<knowledge-sources-root>/<source-id>/<version>/manifest.json
```

The service chooses the latest valid manifest, or the pinned GEM version when configured. A
manifest records source URL/version, retrieval time, request profile, checksums, normalizer,
license, attribution, and coverage. If no primary mirror exists, earthquake/fault providers
fall back to configured legacy paths and warn. The attributed asset installer supplies these
legacy-compatible USGS/GEM files when `peace-knowledge-base` is installed.

Mirror sync is implemented only for:

- `usgs_fdsn_events`: USGS FDSN Event API, optionally bounded;
- `gem_global_active_faults`: pinned GEM source normalized to GeoJSON.

See [installation](installation.md) for commands. Sync is explicit network access and writes
local datasets.

## Earthquake History

Configured sources default to `usgs_fdsn_events,emsc_fdsn_events`, with USGS primary. A query
uses only the first source unless `source`, `sources`, or `source: "all"` selects others. USGS
uses a local mirror/legacy CSV by default; EMSC is a live secondary source. Cross-source
deduplication uses exact event association-ID overlap, not fuzzy time/location matching.

Accepted `provider_options.earthquake_history` keys:

| Key | Values |
| --- | --- |
| `source` | Configured source ID or `all`; mutually exclusive with `sources`. |
| `sources` | Configured source-ID list or comma-separated string. |
| `source_mode` | `local_mirror`, `legacy_asset`, or `live`. |
| `starttime`, `endtime` | Source-compatible timestamp strings. |
| `minmagnitude`, `maxmagnitude` | Numeric magnitude bounds. |
| `reviewstatus`, `catalog`, `contributor` | Source filter strings. |

Example explicit live USGS request:

```json
{
  "include": ["earthquake_history"],
  "provider_options": {
    "earthquake_history": {
      "source": "usgs_fdsn_events",
      "source_mode": "live",
      "starttime": "2025-01-01",
      "minmagnitude": 4.5
    }
  }
}
```

This sends bounds and filters to the USGS service. Source responses and availability are
mutable. A 0-record result only describes the configured filters/source vintage.

## Active Faults

Configured sources default to `gem_global_active_faults,diss_seismogenic_sources`, with GEM
primary. GEM is local-mirror/legacy only. DISS 3.3.1 is a live WFS secondary source for Italy
and surrounding areas and must be selected explicitly.

Accepted options are `source`, `sources`, and `source_mode`; `source` and `sources` are mutually
exclusive. `source_mode` is `local_mirror`, `legacy_asset`, or `live`, but live is accepted only
for live-capable selected sources.

The `auto` geometry engine uses Shapely when installed, otherwise bounding-box intersection.
`bbox` may include false positives for complex features; `shapely` performs geometry
intersection. GEM has documented geographic gaps. The provider always warns when no GEM feature
intersects because that is not proof that no active fault exists.

## Mineral Occurrences

This provider is explicit-only and live-only. It federates:

- `ontario_mineral_deposit_inventory`: an ArcGIS FeatureServer snapshot covering Ontario;
- `sigeom_mineral_occurrences`: a Quebec SIGEOM WFS layer.

Accepted options are `source`, `sources`, and `source_mode`; only `source_mode: "live"` is valid.
By default, all configured mineral sources are considered and out-of-region sources are skipped
with warnings. Rectangular coverage bounds are routing hints, not authoritative province
polygons. The Ontario endpoint is a third-party-republished March 2013 MDI snapshot, not the
continuously updated authoritative Ontario inventory.

Every selected in-coverage source receives the query bounds over HTTP. Empty/out-of-coverage
results explicitly warn against absence claims.

## Earth Engine

`landcover_distribution` reads `ESA/WorldCover/v200` by default and returns percentages by
class. `population_density` reads `WorldPop/GP/100m/pop` and returns population, area, and people
per square kilometre. Both mosaic an image collection and call Earth Engine `reduceRegion` with
configured scale/max pixels and `bestEffort=True`.

Set `GEOMAP_EARTHENGINE_PROJECT`, install the extra, and authenticate through the Earth Engine
client outside this package. These providers accept no provider-specific options. They perform
live remote computation only when explicitly included.

## K2 Lookup And Semantic Providers

Install all five K2 JSON assets from the pinned MIT PEACE repository with:

```bash
stratigraphic-amenity-assets peace-knowledge-base
```

`rock_type`/`rock_age` perform exact then substring lookup over labels. Semantic providers use a Sentence Transformer with
`trust_remote_code=False`; the default model may download from its model host unless
`GEOMAP_SEMANTIC_LOCAL_FILES_ONLY=true`. No provider-specific request options are accepted;
global/per-provider record limits control semantic top-k.

## Caching And Warnings

Provider results are cached at `<cache-root>/knowledge/v2/providers/<provider>/<hash>.json`.
Cache keys include provider/source versions, bounds rounded to four decimal places, limits,
options, query-text hash, and provider config. Cached results preserve items and reconstruct
provider warnings where supported. Caching does not make live source provenance immutable
unless a normalized mirror manifest pins it.

Warnings are non-fatal unless every explicitly requested provider fails. Important classes:

- missing local asset/dependency;
- fallback to a legacy path because no mirror exists;
- source outside geographic coverage;
- empty result is not proof of absence;
- source-specific failure within a federated query;
- unknown, ambiguous, ignored, or incompatible filter/options;
- result truncation, represented by item and bundle count fields;
- overlay geometry outside map bounds, indicating possible CRS mismatch.

Always retain `provider_versions`, item `provenance`, and bundle `trace` with any downstream
claim.
