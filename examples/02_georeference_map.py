"""Fit a georeference from explicit client-read ground control points."""

from __future__ import annotations

import argparse
from pathlib import Path

from stratigraphic_amenity.georef import GroundControlPoint, georeference_bounds


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Map image path (used for display only).")
    parser.add_argument("--crs", required=True, help="Printed map CRS, such as EPSG:26915.")
    parser.add_argument(
        "--gcp",
        action="append",
        nargs=4,
        type=float,
        metavar=("PIXEL_X", "PIXEL_Y", "WORLD_X", "WORLD_Y"),
        required=True,
        help="Ground control point; repeat at least twice.",
    )
    parser.add_argument(
        "--pixel-extent",
        nargs=4,
        type=float,
        required=True,
        metavar=("X0", "Y0", "X1", "Y1"),
    )
    args = parser.parse_args()
    if len(args.gcp) < 2:
        parser.error("--gcp must be provided at least twice")

    ref = georeference_bounds(
        crs=args.crs,
        gcps=[GroundControlPoint(*values) for values in args.gcp],
        pixel_extent=tuple(args.pixel_extent),
    )
    bounds = ref.bounds
    print(f"Map: {args.image.name}")
    print(f"  CRS: {args.crs!r} -> {ref.crs}")
    print(
        f"  bounds (EPSG:4326): lon [{bounds.min_lon:.4f}, {bounds.max_lon:.4f}], "
        f"lat [{bounds.min_lat:.4f}, {bounds.max_lat:.4f}]"
    )
    print(f"  affine fit residual: {ref.residual:.4f} m")

    x0, y0, x1, y1 = args.pixel_extent
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    lon, lat = ref.pixel_to_lonlat(cx, cy)
    bx, by = ref.lonlat_to_pixel(lon, lat)
    print(
        f"  centre pixel ({cx:.0f}, {cy:.0f}) -> "
        f"({lon:.4f}, {lat:.4f}) -> ({bx:.1f}, {by:.1f})"
    )


if __name__ == "__main__":
    main()
