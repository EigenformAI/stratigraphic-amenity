# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-07-28

### Added

* Initial public Stratigraphic Amenity Python SDK and local stdio MCP server.
* Geologic-map registration, processing boundaries, affine georeferencing,
  knowledge-provider queries, legend enrichment, and evidence overlays.
* Opaque `geomap://` resources and capability discovery for agent workflows.
* Explicit optional installation profiles for MCP, georeferencing, local and
  network knowledge, Earth Engine, semantic retrieval, and detector clients.
* Public provenance, security, contribution, support, citation, CI, and trusted
  release infrastructure.
* Attributed installer for the pinned PEACE YOLOv10 runtime, published detector weights, K2
  material, USGS earthquake history, and GEM active-fault data.

### Security

* Kept live network access opt-in and constrained local map access to configured
  roots.
* Kept optional PEACE assets out of Python distributions while enforcing source attribution,
  selected-subtree extraction, archive traversal checks, and detector-weight SHA-256 validation.

[Unreleased]: https://github.com/EigenformAI/stratigraphic-amenity/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/EigenformAI/stratigraphic-amenity/releases/tag/v0.1.0
