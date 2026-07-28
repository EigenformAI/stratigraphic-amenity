"""Process an explicit map image into structured components.

Install `stratigraphic-amenity[detectors]`, then run
`stratigraphic-amenity-assets peace-yolov10-runtime` and
`stratigraphic-amenity-assets peace-layout-detectors` first.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Map image path.")
    parser.add_argument("--dataset-source", default="user-supplied")
    args = parser.parse_args()

    os.environ.setdefault("GEOMAP_DATASET_SOURCE", args.dataset_source)
    from stratigraphic_amenity.map_processing import MapProcessingService

    result = MapProcessingService().process_image(args.image).to_dict()
    print(f"Map: {args.image.name}")
    print(f"  size: {result['size']['width']}x{result['size']['height']}")
    detected = {label: len(dets) for label, dets in result["regions"].items() if dets}
    print(f"  components detected: {detected}")
    print(f"  legend entries: {len(result.get('legend', []))}")
    roles = sorted({artifact.get("role") for artifact in result.get("artifacts", [])})
    print(f"  artifact roles: {roles}")


if __name__ == "__main__":
    main()
