# Repository Guide For Coding Agents

This file is for coding agents modifying Stratigraphic Amenity. Runtime agents using the MCP
server should read [docs/agent-guide.md](docs/agent-guide.md).

## Identity And Scope

- Product: Stratigraphic Amenity
- Distribution: `stratigraphic-amenity`
- Import: `stratigraphic_amenity`
- MCP server name: `stratigraphic-amenity`
- MCP executable: `stratigraphic-amenity-mcp`
- Asset executable: `stratigraphic-amenity-assets`
- Domain protocol identifiers: `geomap_*`, `geomap://`, and `GEOMAP_*` remain unchanged
- Release: 0.1.0, Python 3.11 only, MIT

Do not restore compatibility aliases or sibling-checkout discovery. PEACE runtime, layout
weights, and knowledge assets must flow through `assets/manifest.toml` and the attributed asset
installer; never commit downloaded copies. Do not add private paths, maps, model files,
credentials, or unapproved download URLs.

## Architecture

| Area | Location | Responsibility |
| --- | --- | --- |
| Public exports | `src/stratigraphic_amenity/__init__.py` | Stable top-level service and config exports. |
| Paths | `src/stratigraphic_amenity/paths.py` | XDG defaults and launch-directory resolution. |
| Map processing | `src/stratigraphic_amenity/map_processing/` | Detector boundary, crops, metadata, and cache. |
| Georeferencing | `src/stratigraphic_amenity/georef/` | CRS resolution, affine fitting, and EPSG:4326 bounds. |
| Knowledge | `src/stratigraphic_amenity/knowledge/` | Requests, providers, source mirrors, cache, and rendering. |
| MCP | `src/stratigraphic_amenity/mcp/` | stdio server, schemas, adapter, errors, and resource registry. |
| Asset policy | `assets/manifest.toml` | Release decision for every optional artifact. |
| Examples | `examples/` | User-image, explicit-input demonstrations. |
| Tests | `tests/` | Unit, integration, identity, schema, and self-containment checks. |

Keep the MCP adapter thin: domain behavior belongs in SDK services; MCP code validates,
redacts, persists resource handles, and maps failures to agent-facing envelopes. Providers
must remain lazy so the base import does not require optional dependencies or credentials.

## Setup And Checks

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
uv run python -c "import stratigraphic_amenity as sa; print(sa.__version__)"
```

Install only the profile under test, for example:

```bash
uv sync --group dev --extra mcp --extra geo --extra knowledge-network
uv run pytest tests/test_mcp_server.py tests/test_georef_transform.py
```

The `detectors` and `knowledge-semantic` extras intentionally conflict because they require
different Torch ranges. Test them in separate environments. Live provider tests must be
explicit opt-in; normal tests must use fakes, temporary assets, or recorded fixtures.

## Change Rules

- Follow TDD for behavior changes: add a concise failing test, implement, then run focused and
  full checks.
- Keep JSON Schema, adapter behavior, MCP reference, and tests synchronized when changing a
  tool.
- Keep provider registration, configuration variables, provider reference, and capability
  output synchronized.
- Preserve `stdout` exclusively for stdio JSON-RPC. Diagnostics belong on `stderr` and must not
  expose maps, credentials, prompts, or absolute paths to model-visible output.
- Treat allowed roots as accidental-access controls, not a sandbox. Continue to canonicalize
  paths and reject symlink escapes, unsupported media, stale files, and oversized reads.
- Preserve warnings and provenance through caches. Empty provider output must not be presented
  as proof of geological absence.
- Add any code/model/data artifact to `assets/manifest.toml` with an immutable source, digest,
  license, attribution, destination, policy, and capability mapping before acquisition.
- Examples must require an explicit user image and be offline by default.

## Generated And Local Files

- Regenerate `uv.lock` through `uv`, never edit it by hand.
- Do not commit `.env`, `.venv/`, `.cache/`, `data/`, generated map artifacts, or acquired
  models/data.
- `.env` is not loaded by Python. `.envrc.example` is optional developer ergonomics and must
  remain side-effect free.
- Source and wheel builds must exclude working notes, benchmark runs, caches, local data, and
  secrets. Inspect artifact file lists before release.

## Security Review

For MCP and provider changes, verify filesystem roots, URI ownership, payload limits, path
redaction, network opt-in, credential handling, cache provenance, and error detail exposure.
Never broaden filesystem or network access merely to make a test pass.
