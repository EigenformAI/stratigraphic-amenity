"""Offline stdio fixture server used by the end-to-end MCP test."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

from stratigraphic_amenity.knowledge import Bounds, KnowledgeBundle, KnowledgeItem
from stratigraphic_amenity.map_processing.types import (
    ArtifactRef,
    Detection,
    ImageSize,
    MapProcessingResult,
)
from stratigraphic_amenity.mcp.adapter import GeomapMcpAdapter
from stratigraphic_amenity.mcp.server import _run_stdio, create_server


class FixtureMapService:
    def process_image(self, image_path: str | Path) -> MapProcessingResult:
        artifact = Path(os.environ["GEOMAP_CACHE_ROOT"]) / "fixture-main-map.png"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(Path(image_path).read_bytes())
        return MapProcessingResult(
            name=Path(image_path).stem,
            source="stdio-fixture",
            image_path=Path(image_path),
            size=ImageSize(width=100, height=100),
            regions={
                "main_map": [
                    Detection(
                        label="main_map",
                        bbox=(0, 0, 100, 100),
                        confidence=1.0,
                        artifact_path=str(artifact),
                    )
                ]
            },
            artifacts=[
                ArtifactRef(
                    path=artifact,
                    role="component_crop",
                    stage="hie",
                    bbox=(0, 0, 100, 100),
                    label="main_map",
                    mime_type="image/png",
                )
            ],
        )


class FixtureKnowledgeService:
    def __init__(self) -> None:
        self._registrations = [
            SimpleNamespace(
                id="fixture_provider",
                name="Fixture provider",
                output_keys=("fixture_records",),
                default_enabled=True,
            )
        ]

    def query(self, request) -> KnowledgeBundle:
        bounds = request.bounds or Bounds(-90, 45, -89, 46)
        lon = (bounds.min_lon + bounds.max_lon) / 2
        lat = (bounds.min_lat + bounds.max_lat) / 2
        return KnowledgeBundle(
            bounds=bounds,
            items=[
                KnowledgeItem(
                    id="fixture:item",
                    key="fixture_records",
                    provider="fixture_provider",
                    value=[{"longitude": lon, "latitude": lat, "name": "fixture"}],
                    summary="One deterministic fixture record.",
                    source="test fixture",
                    record_count=1,
                    provenance={"network_access": False},
                )
            ],
            selected_item_ids=None,
            warnings=[],
            provider_versions={"fixture_provider": "1"},
        )

    def enrich_legend_label(self, label: str):
        return SimpleNamespace(
            to_dict=lambda: {
                "label": label,
                "lithology": None,
                "stratigraphic_age": None,
                "items": [],
                "warnings": [],
            }
        )


async def main() -> None:
    adapter = GeomapMcpAdapter(
        knowledge_service_factory=FixtureKnowledgeService,
        map_service_factory=FixtureMapService,
    )
    await _run_stdio(create_server(adapter=adapter))


if __name__ == "__main__":
    asyncio.run(main())
