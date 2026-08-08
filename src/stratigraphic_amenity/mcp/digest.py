"""Compact model-visible projections of structured MCP evidence."""

from __future__ import annotations

import json
from typing import Any, Mapping


def _scalar(value: Any) -> str:
    if value is None:
        return "not_available"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.12g}"
    return str(value).replace("\r", " ").replace("\n", " ")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def build_digest(structured: Mapping[str, Any]) -> str:
    """Project essential fields without dumping the complete structured payload."""

    lines = [f"trace_id: {_scalar(structured.get('trace_id'))}"]
    for key in ("map_id", "map_uri", "source_uri", "mime_type", "georef_uri"):
        if key in structured:
            lines.append(f"{key}: {_scalar(structured[key])}")

    providers = structured.get("providers", [])
    if isinstance(providers, list):
        for provider in sorted(providers, key=lambda item: str(item.get("id", ""))):
            provider_id = _scalar(provider.get("id"))
            if provider.get("ready"):
                lines.append(f"ready_provider: {provider_id}")
            else:
                missing = ", ".join(
                    _scalar(item) for item in provider.get("missing_requirements", [])
                ) or "not_available"
                lines.append(f"unready_provider: {provider_id} (missing: {missing})")

    limits = structured.get("limits")
    if isinstance(limits, Mapping):
        rendered = ", ".join(f"{key}={_scalar(limits[key])}" for key in sorted(limits))
        lines.append(f"limits: {rendered}")

    regions = structured.get("regions")
    if isinstance(regions, Mapping):
        for role, detections in regions.items():
            for detection in detections or []:
                bbox = " ".join(_scalar(value) for value in detection.get("bbox", []))
                confidence = detection.get("confidence")
                confidence_text = _scalar(confidence)
                if confidence is not None and float(confidence) < 0.5:
                    confidence_text += " low_confidence"
                uri = _scalar(detection.get("artifact_uri"))
                lines.append(
                    f"region: {role} | {bbox} | confidence={confidence_text} | artifact_uri={uri}"
                )
        legend_detected = bool(regions.get("legend"))
        lines.append(f"legend_region_detected: {'yes' if legend_detected else 'no'}")
        lines.append(
            "legend_extracted_candidates: "
            f"{len(structured.get('legend', []))} (not a verified map-unit count)"
        )

    affine = structured.get("affine")
    if isinstance(affine, Mapping):
        coefficients = affine.get("coefficients") or [
            affine.get(key) for key in ("a", "b", "c", "d", "e", "f")
        ]
        lines.append("affine: " + " ".join(_scalar(value) for value in coefficients))
        for key, label in (
            ("residual", "residual"),
            ("residual_units", "residual_units"),
            ("residual_m", "residual_m"),
            ("residual_diagnostic", "residual_diagnostic"),
            ("fit_method", "fit_method"),
            ("gcp_count", "gcp_count"),
            ("crs", "crs"),
            ("holdout_error", "holdout_error_m"),
        ):
            lines.append(f"{label}: {_scalar(structured.get(key))}")
        if "gcp_pixel_errors" in structured:
            lines.append(
                "gcp_pixel_errors: "
                + " ".join(_scalar(value) for value in structured["gcp_pixel_errors"])
            )
        if "bounds" in structured:
            lines.append(f"bounds: {_json(structured['bounds'])}")

    if "bundle_uri" in structured:
        lines.append(f"bundle_uri: {_scalar(structured['bundle_uri'])}")
    record_counts = structured.get("record_counts")
    if isinstance(record_counts, Mapping):
        counts = ", ".join(
            f"{provider}={_scalar(record_counts[provider])}" for provider in sorted(record_counts)
        )
        lines.append(f"provider_records: {counts or 'none'}")
    for key in ("total_records_found", "total_records_returned", "truncated"):
        if key in structured:
            lines.append(f"{key}: {_scalar(structured[key])}")

    resources = structured.get("resources", [])
    if isinstance(resources, list):
        for resource in resources:
            if isinstance(resource, Mapping) and resource.get("uri"):
                lines.append(
                    f"resource_uri: {_scalar(resource['uri'])} | "
                    f"mime_type={_scalar(resource.get('mime_type'))}"
                )

    for warning in structured.get("warnings", []) or []:
        lines.append(f"warning: {_scalar(warning)}")
    return "\n".join(lines)


def build_error_digest(
    *,
    code: str,
    trace_id: str,
    details: Mapping[str, Any] | None = None,
    recovery_hints: list[str] | None = None,
    cause: Mapping[str, Any] | None = None,
) -> str:
    lines = [f"error.code: {_scalar(code)}", f"trace_id: {_scalar(trace_id)}"]
    if details:
        lines.append(f"details: {_json(details)}")
    for hint in recovery_hints or []:
        lines.append(f"recovery_hint: {_scalar(hint)}")
    if cause:
        lines.append(f"cause: {_json(cause)}")
    return "\n".join(lines)


def append_digest(summary: str, digest: str) -> str:
    return f"{summary}\n\nEvidence digest:\n{digest}"
