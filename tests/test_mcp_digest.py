from stratigraphic_amenity.mcp.digest import build_digest, build_error_digest
from stratigraphic_amenity.mcp.schemas import success_result


def test_digest_surfaces_core_evidence_fields():
    structured = {
        "trace_id": "trace-1",
        "map_id": "map-1",
        "map_uri": "geomap://maps/map-1",
        "source_uri": "geomap://maps/map-1/source",
        "mime_type": "image/png",
        "regions": {
            "main_map": [
                {
                    "bbox": [1, 2, 3, 4],
                    "confidence": 0.49,
                    "artifact_uri": "geomap://artifacts/crop.png",
                }
            ],
            "legend": [],
        },
        "legend": [],
        "warnings": ["legend_not_detected: 1 others region may contain it"],
    }

    digest = build_digest(structured)

    assert "trace_id: trace-1" in digest
    assert "map_uri: geomap://maps/map-1" in digest
    assert "region: main_map | 1 2 3 4 | confidence=0.49 low_confidence" in digest
    assert "artifact_uri=geomap://artifacts/crop.png" in digest
    assert "legend_region_detected: no" in digest
    assert "legend_extracted_candidates: 0 (not a verified map-unit count)" in digest
    assert "warning: legend_not_detected" in digest


def test_digest_surfaces_georef_query_capabilities_and_resources():
    digest = build_digest(
        {
            "trace_id": "trace-2",
            "affine": {"coefficients": [1, 0, 2, 0, -1, 3]},
            "crs": "EPSG:4284",
            "residual": 0.02,
            "residual_units": "degree",
            "residual_m": 1200,
            "residual_diagnostic": True,
            "fit_method": "affine-least-squares",
            "gcp_count": 4,
            "holdout_error": 7000,
            "bounds": {"min_lon": 1, "min_lat": 2, "max_lon": 3, "max_lat": 4},
            "bundle_uri": "geomap://bundles/b.json",
            "record_counts": {"onegeology": 2},
            "limits": {"max_source_bytes": 10, "max_resource_read_bytes": 5},
            "providers": [
                {"id": "ready-provider", "ready": True, "missing_requirements": []},
                {"id": "blocked-provider", "ready": False, "missing_requirements": ["token"]},
            ],
            "resources": [{"uri": "geomap://overlays/o.svg", "mime_type": "image/svg+xml"}],
        }
    )

    for key in (
        "affine:",
        "residual_m: 1200",
        "fit_method: affine-least-squares",
        "holdout_error_m: 7000",
        "bundle_uri: geomap://bundles/b.json",
        "provider_records: onegeology=2",
        "ready_provider: ready-provider",
        "unready_provider: blocked-provider (missing: token)",
        "limits: max_resource_read_bytes=5, max_source_bytes=10",
        "resource_uri: geomap://overlays/o.svg",
    ):
        assert key in digest


def test_success_result_appends_digest_to_both_text_surfaces():
    result = success_result(structured={"map_id": "m"}, text_summary="Registered.", trace_id="t")

    text = result["content"][0]["text"]
    assert "Evidence digest:" in text
    assert "trace_id: t" in text
    assert result["structuredContent"]["text_summary"] == text


def test_error_digest_surfaces_actionable_envelope():
    digest = build_error_digest(
        code="oversize_image",
        trace_id="trace-error",
        details={"observed_bytes": 20, "limit_bytes": 10},
        recovery_hints=["Use a smaller image."],
        cause={"type": "limit"},
    )

    assert "error.code: oversize_image" in digest
    assert "trace_id: trace-error" in digest
    assert 'details: {"limit_bytes":10,"observed_bytes":20}' in digest
    assert "recovery_hint: Use a smaller image." in digest
    assert 'cause: {"type":"limit"}' in digest
