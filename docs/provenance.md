# Provenance And Third-Party Boundaries

This page records implementation lineage, release asset decisions, and third-party source
terms for Stratigraphic Amenity 0.1.0. It is a technical provenance record, not legal advice.

## Project Identity And Lineage

Stratigraphic Amenity is an independent project. The former repository name was
`peace-tool-pool`; version 0.1.0 is a clean-break rename with distribution
`stratigraphic-amenity`, import `stratigraphic_amenity`, and executable
`stratigraphic-amenity-mcp`.

The project derives its motivating HIE, DKI, and PEQA workflow from Microsoft PEACE:

- repository: [microsoft/PEACE](https://github.com/microsoft/PEACE);
- reviewed source revision: [`da994841fc97e5a19e3068a34a86297d17f3f3e2`](https://github.com/microsoft/PEACE/tree/da994841fc97e5a19e3068a34a86297d17f3f3e2);
- paper: [Empowering Geologic Map Holistic Understanding with MLLMs](https://arxiv.org/abs/2501.06184);
- benchmark dataset page: [microsoft/PEACE on Hugging Face](https://huggingface.co/datasets/microsoft/PEACE).

Repository code adapted from that lineage includes map image operations, legend pairing/color
handling, detector adapter interfaces, component/legend metadata shapes, and the high-level HIE
service sequence. Stratigraphic Amenity adds independently organized service/config boundaries,
XDG paths, affine georeferencing, generalized knowledge providers and source manifests,
persistent/redacted MCP resources, structured errors/readiness, caching, and overlay rendering.

PEACE is licensed under the
[MIT License](https://github.com/microsoft/PEACE/blob/da994841fc97e5a19e3068a34a86297d17f3f3e2/LICENSE).
The Stratigraphic Amenity project code is also MIT. PEACE's vendored Ultralytics runtime remains
AGPL-3.0; USGS earthquake data is CC0/public domain and GEM active-fault data remains CC BY-SA
4.0. See the short top-level `NOTICE`.

Stratigraphic Amenity is not affiliated with, sponsored by, or endorsed by Microsoft.

## Release Asset Manifest

`assets/manifest.toml` is the release control for optional code, model, and data artifacts.
Python distributions do not bundle them; the installer retrieves them from attributed upstream
sources into the XDG data root.

| Asset ID | Upstream | Terms | Installer policy |
| --- | --- | --- | --- |
| `peace-yolov10-runtime` | Pinned PEACE commit, `dependencies/ultralytics` | `AGPL-3.0-only` | `source-sync`; selected patched tree SHA-256 `f4b4144bb778543a66dfd86f3ea7b23388a378a02ac708aa91fb0b9b64f21b74`. |
| `peace-layout-detectors` | PEACE quick-start Google Drive file ID `1f7dUdfA_W8He9czG6SoYQBmUsSPrA6MZ` | MIT, attributed to PEACE authors | `download-only`; archive SHA-256 `10701bba7a94f54cbd79cae79ca0a79eba54b82d7e8552e5a78ed5b2dcbb09da`. |
| `peace-knowledge-base` | Pinned PEACE commit, `dependencies/knowledge` | K2 MIT; USGS CC0/public domain; GEM CC BY-SA 4.0 | `source-sync`; selected tree SHA-256 `3fb1b29206667d94c51a8b1a666557aee4dfe54f7f98aacd81c5106022ac0192`. |

PEACE states that its modified Ultralytics use is
[AGPL-3.0](https://github.com/microsoft/PEACE#license). The installer preserves that boundary and
removes PEACE's parent-directory `sys.path` hook before activation; the runtime is dynamically
loaded from its managed data directory. The runtime's AGPL terms are not changed by PEACE's or
Stratigraphic Amenity's MIT license.

The detector archive is the file linked by PEACE's published quick start. It is downloaded from
that source rather than mirrored and is accepted only when its fixed SHA-256 matches. The K2,
USGS, and GEM files are source-synced directly from the pinned PEACE revision and accepted only
when the deterministic path-and-content digest of each extracted tree matches the manifest.

## Maps And Examples

No map or benchmark image is bundled or automatically downloaded. Every example requires a
user-supplied image. Users are responsible for lawful access and use of that image. A map being
publicly viewable is not treated as permission to redistribute it.

GeoMap-Bench is referenced for research context only and is not included in the distribution.

## Knowledge Sources

Provider outputs carry runtime provenance. A normalized mirror manifest records source URL,
version, retrieval time, request profile, normalizer version, checksum, license, citation,
attribution, and coverage. Live queries cannot be reproduced from a URL alone; retain query
bounds/options, source version information, returned items, and retrieval context.

| Source ID | Authority/use | Terms recorded by the source registry | Release treatment |
| --- | --- | --- | --- |
| `usgs_fdsn_events` | USGS Earthquake Hazards Program FDSN Event API | CC0/public domain; see [USGS copyright and credits](https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits) | Installed PEACE snapshot, explicit mirror sync, or explicit live request. |
| `emsc_fdsn_events` | EMSC SeismicPortal event service | See [EMSC service/source policy](https://www.seismicportal.eu/fdsn-wsevent.html) | Explicit live secondary source; no bundled snapshot. |
| `gem_global_active_faults` | GEM Global Active Faults Database, Zenodo 3376300 | [CC BY-SA 4.0](https://github.com/GEMScienceTools/gem-global-active-faults/blob/master/LICENSE.txt) | PEACE snapshot asset or explicit source sync to a local normalized mirror; not bundled in Python distributions. Attribution and share-alike apply to derived distributions. |
| `diss_seismogenic_sources` | DISS 3.3.1, INGV | See [DISS data terms](https://diss.ingv.it/data) | Explicit live regional WFS; no bundled snapshot. |
| `ontario_mineral_deposit_inventory` | Ontario mineral inventory prototype service | [Open Government Licence - Ontario](https://www.ontario.ca/page/open-government-licence-ontario) | Explicit live regional query. Endpoint is a third-party March 2013 MDI snapshot; validate authority/vintage before reuse. |
| `sigeom_mineral_occurrences` | SIGEOM, Gouvernement du Quebec | Registry records CC BY 4.0 with exact-resource verification required before redistribution | Explicit live regional WFS; no bundled snapshot. |
| `ESA/WorldCover/v200` | ESA WorldCover through Earth Engine | See [ESA WorldCover terms](https://esa-worldcover.org/en/data-access) | Explicit live Earth Engine computation; no data bundled. |
| `WorldPop/GP/100m/pop` | WorldPop through Earth Engine | See [WorldPop terms](https://www.worldpop.org/terms_and_conditions) and selected dataset metadata | Explicit live Earth Engine computation; no data bundled. |

The Ontario prototype's endpoint provenance is weaker than its authority label: the running
service identifies a republished 2013 snapshot while the authoritative inventory is maintained
through Ontario's current geoscience data portals. Results must preserve that caveat. SIGEOM's
registry license string also requires verification against exact resource metadata before any
redistribution.

## Semantic Model

The configured default model name is
[`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2).
It is not bundled. After K2 installation, the model library may download model files unless
local-only mode is enabled. Record an immutable model revision
and review its model card/license before reproducible or redistributed use. Runtime loading sets
`trust_remote_code=False`.

## Dependency Licenses

Python dependencies are not relicensed as project code. Their package metadata and upstream
licenses govern use. Notable optional boundaries include the MCP Python SDK/jsonschema, NumPy,
pyproj, Pillow/OpenCV/matplotlib, pandas/Shapely, httpx, Google Earth Engine API, PyTorch,
torchvision, Transformers, and Sentence Transformers. Environment resolution alone is not a
license audit; release builders should retain dependency metadata/SBOMs for the exact profile.

## Redistribution Rules

- Do not bundle or download an artifact outside the manifest. Entries require a pinned source,
  license/attribution, destination, capability mapping, affirmative policy, extraction bound,
  and either an archive or extracted-tree SHA-256 digest.
- Do not treat the project's MIT license as covering upstream models or data.
- Preserve provider item provenance, bundle warnings, source manifests, and required
  attribution with exported results.
- Do not present an empty provider response as proof of absence, particularly outside or near
  documented coverage gaps.
- Obtain image-level rights before distributing any example map or derived crop.
- Re-review live endpoint terms and exact dataset versions before publishing cached responses or
  derived datasets.
