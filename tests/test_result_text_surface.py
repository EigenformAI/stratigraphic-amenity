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


def test_capabilities_summary_states_what_is_not_ready():
    summary = _capabilities_summary(_caps(processing_ready=False, missing=3), provider_count=2)

    assert "map_processing" in summary
    assert "not ready" in summary.lower()
    assert "3" in summary


def test_capabilities_summary_points_at_the_remedy_when_processing_is_blocked():
    summary = _capabilities_summary(_caps(processing_ready=False, missing=3), provider_count=2)

    assert "geomap_prepare_detectors" in summary


def test_capabilities_summary_omits_the_remedy_when_preparation_is_withheld():
    summary = _capabilities_summary(
        _caps(processing_ready=False, missing=1, preparation=False), provider_count=0
    )

    assert "geomap_prepare_detectors" not in summary


def test_capabilities_summary_confirms_readiness_when_nothing_is_missing():
    summary = _capabilities_summary(_caps(processing_ready=True), provider_count=2)

    assert "not ready" not in summary.lower()
    assert "ready" in summary.lower()


def test_capabilities_summary_reports_ready_and_registered_provider_counts():
    summary = _capabilities_summary(
        _caps(processing_ready=True), provider_count=2
    )

    assert "1 of 2 knowledge provider" in summary
    assert "All capabilities are ready" not in summary
    assert "partial" in summary.lower()


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


def test_summary_names_the_source_frame():
    summary = _processing_summary(_structured(labels=[None]), map_id="m", has_preview=False)

    assert "1600" in summary and "1946" in summary
    assert "source" in summary.lower()


def test_summary_states_unlabeled_count_and_forbids_inference():
    summary = _processing_summary(
        _structured(labels=[None, None, "Gneiss"]), map_id="m", has_preview=False
    )

    assert "2 of 3" in summary
    assert "no ocr" in summary.lower()
    assert "do not infer" in summary.lower()


def test_summary_is_quiet_when_every_label_was_extracted():
    summary = _processing_summary(
        _structured(labels=["Gneiss", "Gabbro"]), map_id="m", has_preview=False
    )

    assert "do not infer" not in summary.lower()


def test_summary_warns_that_an_attached_preview_is_a_different_frame():
    summary = _processing_summary(_structured(labels=["Gneiss"]), map_id="m", has_preview=True)

    assert "preview" in summary.lower()
    assert "downsampled" in summary.lower()


def test_summary_omits_preview_caution_when_none_is_attached():
    summary = _processing_summary(_structured(labels=["Gneiss"]), map_id="m", has_preview=False)

    assert "downsampled" not in summary.lower()
