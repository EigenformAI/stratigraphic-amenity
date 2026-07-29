# Contributing to Stratigraphic Amenity

Thank you for helping make geologic-map tooling more portable, inspectable,
and useful. By participating, you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Before You Start

Use [GitHub Discussions](https://github.com/EigenformAI/stratigraphic-amenity/discussions)
for support or early design discussion. Use an issue for a confirmed bug or a
scoped proposal. Report vulnerabilities privately as described in
[SECURITY.md](SECURITY.md).

## Development Setup

Stratigraphic Amenity supports Python 3.11. Install
[uv](https://docs.astral.sh/uv/), clone the repository, and create the
development environment:

```bash
uv sync --group dev --extra mcp --extra geo --extra knowledge-local --extra knowledge-network
uv run pytest
uv run ruff check .
```

The default package is deliberately lightweight. Optional profiles should be
installed only when needed. The `detectors` and `knowledge-semantic` profiles
have incompatible PyTorch constraints and must be resolved in separate
environments.

## Development Process

For behavior changes, follow test-driven development:

1. Add a concise test that demonstrates the desired behavior and fails for the
   expected reason.
2. Implement the smallest change that makes the test pass.
3. Run the focused test, then the complete applicable test suite and Ruff.
4. Update maintained user or reference documentation when a public contract,
   configuration value, tool schema, or workflow changes.

Keep the base install asset-free and network-free. Tests must use local
fixtures or fakes by default; live network and licensed model integration
tests must be explicit opt-ins.

## Provenance and Dependencies

Every contribution must identify copied or adapted code. Include the source
URL, immutable revision, author or copyright holder, and license in the pull
request. Do not submit code, models, weights, maps, generated data, or other
assets unless their redistribution terms and provenance are documented.

Do not bundle downloaded PEACE runtime, weights, or knowledge files in a change. Update the
attributed manifest/installer instead. A new downloadable asset requires a pinned source,
license, attribution, destination, explicit distribution policy, extraction bound, and an archive
or deterministic extracted-tree digest.

New runtime dependencies should be optional unless required by the base API.
Explain their license, maintenance status, and why the standard library or an
existing dependency is insufficient.

## Pull Requests

Keep pull requests focused and describe externally visible changes. Complete
the pull request checklist, link related issues, and include commands and
results used for verification. Do not include credentials, local paths,
private URLs, downloaded assets, caches, or generated benchmark output.

Maintainers may ask for changes to preserve bounded outputs, provenance,
offline defaults, MCP stdout integrity, filesystem restrictions, or optional
dependency boundaries. Contributions are accepted under the repository's MIT
License.
