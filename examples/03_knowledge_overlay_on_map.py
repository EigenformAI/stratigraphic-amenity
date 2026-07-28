"""Render a supplied knowledge bundle, or explicitly opt into live providers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stratigraphic_amenity.georef import GroundControlPoint, georeference_bounds
from stratigraphic_amenity.knowledge import Bounds, KnowledgeBundle, KnowledgeItem, KnowledgeService
from stratigraphic_amenity.knowledge.visualization import (
    extract_knowledge_overlay,
    render_knowledge_overlay_on_image,
)


PROVIDERS = ("mineral_occurrences", "active_faults", "earthquake_history")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--bundle", type=Path, help="Recorded knowledge/v2 bundle JSON.")
    parser.add_argument("--live", action="store_true", help="Allow live network provider calls.")
    parser.add_argument("--crs", required=True)
    parser.add_argument("--gcp", action="append", nargs=4, type=float, required=True)
    parser.add_argument("--pixel-extent", nargs=4, type=float, required=True)
    parser.add_argument("--out", type=Path, default=Path("knowledge-overlay.png"))
    parser.add_argument("--max-records", type=int, default=200)
    args = parser.parse_args()
    if len(args.gcp) < 2:
        parser.error("--gcp must be provided at least twice")
    if args.live == (args.bundle is not None):
        parser.error("choose exactly one of --bundle or --live")

    ref = georeference_bounds(
        crs=args.crs,
        gcps=[GroundControlPoint(*values) for values in args.gcp],
        pixel_extent=tuple(args.pixel_extent),
    )
    if args.live:
        service = KnowledgeService.from_env()
        service.config.max_records_per_provider = args.max_records
        bundle = service.query_bounds(ref.bounds, include=PROVIDERS)
    else:
        bundle = _load_bundle(args.bundle)
    overlay = extract_knowledge_overlay(bundle)

    render_knowledge_overlay_on_image(
        overlay,
        ref,
        args.image,
        args.out,
        title=f"{args.image.name} - knowledge evidence",
    )

    counts = {item.key: item.record_count for item in bundle.items}
    plotted = sum(1 for item in overlay.items if item.kind in {"result_point", "result_bbox"})
    print(f"Map: {args.image.name}")
    print(f"  knowledge counts: {counts}")
    print(f"  annotations drawn: {plotted}  (out of map: {len(overlay.out_of_bounds)})")
    print(f"  annotated map written: {args.out}")


def _load_bundle(path: Path) -> KnowledgeBundle:
    data = json.loads(path.read_text(encoding="utf-8"))
    bounds = Bounds(**data["bounds"]) if data.get("bounds") else None
    return KnowledgeBundle(
        bounds=bounds,
        items=[KnowledgeItem.from_dict(item) for item in data.get("items", [])],
        selected_item_ids=data.get("selected_item_ids"),
        warnings=list(data.get("warnings", [])),
        provider_versions=dict(data.get("provider_versions", {})),
        trace=data.get("trace"),
        schema_version=str(data.get("schema_version", "knowledge/v2")),
    )


if __name__ == "__main__":
    main()
