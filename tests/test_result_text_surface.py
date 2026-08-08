"""Guidance must survive clients that surface only text.

Round-2 run E proved an MCP host may show the model a tool's text and inline image
while never surfacing structuredContent. Anything the model must not get wrong has to
be in the text, not only in a structured field.
"""

from stratigraphic_amenity.mcp.adapter import _capabilities_summary, _processing_summary


def _caps(*, processing_ready: bool, missing: int = 0, preparation: bool = True):
    return {
        "map_registration": {"ready": True, "missing_requirements": []},
        "map_processing": {
            "ready": processing_ready,
            "missing_requirements": [f"requirement {index}" for index in range(missing)],
        },
        "detector_preparation": {"ready": preparation, "missing_requirements": []},
        "georeferencing": {"ready": True, "missing_requirements": []},
        "knowledge_query": {
            "ready": True,
            "missing_requirements": [],
            "ready_provider_count": 1,
            "registered_provider_count": 2,
        },
    }


def test_capabilities_summary_scenarios():
    scenarios = (
        {
            "capabilities": _caps(processing_ready=False, missing=3),
            "provider_count": 2,
            "contains": ("map_processing", "3", "geomap_prepare_detectors"),
            "lower_contains": ("not ready",),
            "absent": (),
        },
        {
            "capabilities": _caps(processing_ready=False, missing=1, preparation=False),
            "provider_count": 0,
            "contains": (),
            "lower_contains": (),
            "absent": ("geomap_prepare_detectors",),
        },
        {
            "capabilities": _caps(processing_ready=True),
            "provider_count": 2,
            "contains": ("1 of 2 knowledge provider",),
            "lower_contains": ("partial",),
            "absent": ("All capabilities are ready",),
        },
    )

    for scenario in scenarios:
        summary = _capabilities_summary(
            scenario["capabilities"], provider_count=scenario["provider_count"]
        )
        for expected in scenario["contains"]:
            assert expected in summary
        for expected in scenario["lower_contains"]:
            assert expected in summary.lower()
        for unexpected in scenario["absent"]:
            assert unexpected not in summary


def _structured(*, labels: list[str | None], width: int = 1600, height: int = 1946):
    return {
        "size": {"width": width, "height": height},
        "regions": {"main_map": [{"bbox": [0, 0, 1, 1]}], "legend": [{"bbox": [0, 0, 1, 1]}]},
        "legend": [
            {
                "label": label,
                "label_extraction": "extracted" if label else "not_available",
            }
            for label in labels
        ],
    }


def test_processing_summary_scenarios():
    scenarios = (
        {
            "structured": _structured(labels=[None]),
            "has_preview": False,
            "contains": ("1600", "1946"),
            "lower_contains": ("source",),
        },
        {
            "structured": _structured(labels=[None, None, "Gneiss"]),
            "has_preview": False,
            "contains": ("2 of 3",),
            "lower_contains": ("no ocr", "do not infer"),
        },
        {
            "structured": _structured(labels=["Gneiss"]),
            "has_preview": True,
            "contains": (),
            "lower_contains": ("preview", "downsampled"),
        },
    )

    for scenario in scenarios:
        summary = _processing_summary(
            scenario["structured"], map_id="m", has_preview=scenario["has_preview"]
        )
        for expected in scenario["contains"]:
            assert expected in summary
        for expected in scenario["lower_contains"]:
            assert expected in summary.lower()
        assert "legend region: detected" in summary.lower()
        assert "legend extracted candidates:" in summary.lower()
        assert "legend entries" not in summary.lower()
