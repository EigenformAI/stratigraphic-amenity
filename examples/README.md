# Examples

Every example accepts an explicit user-supplied map path. No map, model, or private checkout is
bundled. Run `python examples/<name>.py --help` for the complete argument contract.

- `01_process_map.py` demonstrates HIE after installing the `detectors` extra plus
  `peace-yolov10-runtime` and `peace-layout-detectors` assets.
- `02_georeference_map.py` is asset-free and takes a CRS, at least two GCPs, and a pixel extent.
- `03_knowledge_overlay_on_map.py` is offline by default with `--bundle PATH`. Network providers
  are called only with `--live`; their responses and availability are mutable.

Example:

```bash
uv run --extra geo python examples/02_georeference_map.py map.png \
  --crs EPSG:26915 \
  --gcp 0 0 660000 5400000 \
  --gcp 1000 1000 690000 5370000 \
  --pixel-extent 0 0 1000 1000
```

Map labels, CRS text, and control points must come from the operator or client VLM. The examples
do not include OCR, a VLM, or final PEQA answer generation.
