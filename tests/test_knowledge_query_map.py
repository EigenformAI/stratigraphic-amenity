"""KnowledgeService.query_map: derive Bounds (explicit or via georef) + legend
labels from map metadata, then delegate to query().

Tests spy on .query so they are deterministic and independent of local knowledge
assets; the real end-to-end path is exercised by scripts/demo_georef_knowledge.py.
"""

import pytest

from stratigraphic_amenity.knowledge import Bounds, KnowledgeService


def _service_with_spy():
    svc = KnowledgeService.from_env()
    captured: dict = {}

    def spy(request):
        captured["request"] = request
        return "BUNDLE"

    svc.query = spy  # type: ignore[assignment]
    return svc, captured


def test_query_map_constructs_request_from_explicit_bounds():
    svc, captured = _service_with_spy()
    out = svc.query_map(
        {"bounds": {"min_lon": -91.0, "min_lat": 48.0, "max_lon": -90.0, "max_lat": 49.0}},
        include=("earthquake_history",),
        question="what deposits occur here?",
    )
    assert out == "BUNDLE"
    req = captured["request"]
    assert isinstance(req.bounds, Bounds)
    assert req.bounds.max_lat == 49.0
    assert req.include == ("earthquake_history",)
    assert req.query_text == "what deposits occur here?"


def test_query_map_integrates_georef_bounds():
    svc, captured = _service_with_spy()
    metadata = {
        "georef": {
            "crs": "UTM N83 Zone 15",
            "gcps": [
                [167, 99, 660000, 5400000],
                [1175, 1238, 690000, 5360000],
            ],
            "pixel_extent": [23, 20, 1332, 1344],
        }
    }
    svc.query_map(metadata, include=("active_faults",))
    bounds = captured["request"].bounds
    assert bounds.crs == "EPSG:4326"
    assert -92 < bounds.min_lon and bounds.max_lon < -89
    assert 47 < bounds.min_lat and bounds.max_lat < 50


def test_query_map_handles_legend_metadata_and_requires_queryable_input():
    svc, captured = _service_with_spy()
    bounds = {"min_lon": -91, "min_lat": 48, "max_lon": -90, "max_lat": 49}
    scenarios = [
        (
            [{"label": "gabbro"}, {"label": ""}, {"label": "iron formation"}],
            {"gabbro", "iron formation"},
        ),
        ([[0, {"text": "pegmatite"}], [1, {"text": ""}]], {"pegmatite"}),
    ]

    for legend, expected_labels in scenarios:
        svc.query_map({"bounds": bounds, "legend": legend})
        labels = captured["request"].legend_labels
        assert expected_labels.issubset(labels)
        assert "" not in labels

    with pytest.raises(ValueError):
        svc.query_map({})
