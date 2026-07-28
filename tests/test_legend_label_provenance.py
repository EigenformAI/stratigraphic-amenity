"""Unextracted legend labels must read as absent, not as blank-and-fillable.

Both round-2 MCP agents reported invented lithology names for entries whose text
fields were empty strings.
"""

from types import SimpleNamespace

from stratigraphic_amenity.map_processing.types import ImageSize, LegendEntry
from stratigraphic_amenity.mcp.schemas import map_processing_result_to_mcp


class _Registry:
    def map_public(self, map_id):
        return {"map_id": map_id, "source_uri": "geomap://x", "map_uri": "geomap://maps/x"}

    def register_artifact(self, *_args, **_kwargs):  # pragma: no cover - no artifacts here
        raise AssertionError("no artifacts in this fixture")


def _entry(entry_id: int, label: str = "") -> LegendEntry:
    return LegendEntry(
        id=entry_id,
        color_bbox=(0, 0, 10, 10),
        text_bbox=(10, 0, 40, 10),
        color_rgb=(1, 2, 3),
        color_hex="#010203",
        color_name="Pink",
        label=label,
    )


def _result(*entries: LegendEntry):
    return SimpleNamespace(
        artifacts=[],
        regions={},
        legend=list(entries),
        size=ImageSize(width=100, height=200),
        created_date="2026-07-28",
        name="map",
        version="1",
        source="usgs",
        information={},
        faults={},
    )


def _payload(*entries: LegendEntry):
    return map_processing_result_to_mcp(_result(*entries), registry=_Registry(), map_id="x")


def test_unextracted_label_is_null_not_empty_string():
    entry = _payload(_entry(0))["legend"][0]

    assert entry["label"] is None
    assert entry["label_extraction"] == "not_available"


def test_payload_warns_that_labels_are_not_extracted():
    warnings = _payload(_entry(0), _entry(1))["warnings"]

    assert any("label" in warning.lower() for warning in warnings)
    assert any("ocr" in warning.lower() for warning in warnings)


def test_extracted_label_is_preserved_and_marked():
    entry = _payload(_entry(0, label="Gneiss"))["legend"][0]

    assert entry["label"] == "Gneiss"
    assert entry["label_extraction"] == "extracted"


def test_no_warning_when_every_label_is_present():
    warnings = _payload(_entry(0, label="Gneiss"))["warnings"]

    assert not any("label" in warning.lower() for warning in warnings)


def test_regions_declare_the_source_coordinate_frame():
    """Run A reported preview-frame boxes as detector output; frames must be explicit."""

    payload = _payload(_entry(0))

    assert payload["coordinate_frame"] == "source"
    assert payload["size"]["width"] == 100
