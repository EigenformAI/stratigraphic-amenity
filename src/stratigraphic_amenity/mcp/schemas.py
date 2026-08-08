"""JSON schemas and redaction/conversion helpers for MCP tool payloads."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Mapping

from ..knowledge.types import SCHEMA_VERSION as KNOWLEDGE_SCHEMA_VERSION
from ..map_processing.types import SCHEMA_VERSION as MAP_PROCESSING_SCHEMA_VERSION
from .digest import append_digest, build_digest
from .resources import ResourceRegistry


JSON_SCHEMA = "https://json-schema.org/draft/2020-12/schema"

PATH_KEYS = {
    "asset_path",
    "artifact_path",
    "image_path",
    "local_path",
    "path",
    "source_path",
}


def new_trace_id() -> str:
    return uuid.uuid4().hex


def redact_paths(value: Any) -> Any:
    """Recursively remove local filesystem paths from model-visible payloads."""

    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_string = str(key)
            if key_string in PATH_KEYS and isinstance(item, (str, Path)):
                redacted[key_string] = "<redacted>"
            else:
                redacted[key_string] = redact_paths(item)
        return redacted
    if isinstance(value, list):
        return [redact_paths(item) for item in value]
    if isinstance(value, tuple):
        return [redact_paths(item) for item in value]
    if isinstance(value, Path):
        return "<redacted>"
    if isinstance(value, str) and _looks_like_local_path(value):
        return "<redacted>"
    return value


def map_processing_result_to_mcp(
    result: Any,
    *,
    registry: ResourceRegistry,
    map_id: str,
) -> dict[str, Any]:
    """Convert an SDK ``MapProcessingResult`` to a path-redacted MCP payload."""

    map_info = registry.map_public(map_id)
    artifacts: list[dict[str, Any]] = []
    artifact_by_path: dict[str, dict[str, Any]] = {}
    for artifact in result.artifacts:
        public = registry.register_artifact(
            artifact.path,
            role=artifact.role,
            stage=artifact.stage,
            map_id=map_id,
            bbox=list(artifact.bbox) if artifact.bbox is not None else None,
            label=artifact.label,
            mime_type=artifact.mime_type,
        )
        artifact_by_path[str(Path(artifact.path).resolve())] = public
        artifacts.append(public)

    regions: dict[str, list[dict[str, Any]]] = {}
    for label, detections in result.regions.items():
        converted_detections: list[dict[str, Any]] = []
        for detection in detections:
            data = detection.to_dict()
            raw_artifact_path = data.pop("artifact_path", None)
            if raw_artifact_path:
                canonical = str(Path(raw_artifact_path).resolve())
                public_artifact = artifact_by_path.get(canonical)
                if public_artifact is None:
                    public_artifact = registry.register_artifact(
                        raw_artifact_path,
                        role="component_crop",
                        stage="hie",
                        map_id=map_id,
                        bbox=data.get("bbox"),
                        label=label,
                    )
                    artifact_by_path[canonical] = public_artifact
                    artifacts.append(public_artifact)
                data["artifact_uri"] = public_artifact["uri"]
            converted_detections.append(data)
        regions[label] = converted_detections

    legend = [_legend_entry_to_mcp(entry) for entry in result.legend]
    warnings: list[str] = []
    if any(entry["label_extraction"] == "not_available" for entry in legend):
        warnings.append(
            "Legend labels were not extracted; this build ships no OCR. Entries with "
            "label_extraction 'not_available' have no transcribed text. Do not infer them "
            "from an image; ask the user or a separate OCR/VLM system."
        )
    if not regions.get("legend") and regions.get("others"):
        candidate_uris = [
            entry.get("artifact_uri") for entry in regions["others"] if entry.get("artifact_uri")
        ]
        warnings.append(
            "legend_not_detected: no legend region was found; "
            f"{len(candidate_uris)} 'others' region(s) may contain it: "
            + (", ".join(candidate_uris) if candidate_uris else "no readable candidate artifacts")
        )

    payload = {
        "schema_version": MAP_PROCESSING_SCHEMA_VERSION,
        "date": result.created_date,
        "name": result.name,
        "version": result.version,
        "source": result.source,
        "source_uri": map_info["source_uri"],
        "map_uri": map_info["map_uri"],
        "size": result.size.to_dict(),
        # Every box below is in the full-resolution source frame. Inline previews are
        # downsampled and carry coordinate_frame 'preview'; the two must not be mixed.
        "coordinate_frame": "source",
        "regions": regions,
        "legend": legend,
        "artifacts": artifacts,
        "information": redact_paths(result.information),
        "faults": redact_paths(result.faults),
        "source_path_redacted": True,
        "warnings": warnings,
    }
    return redact_paths(payload)


def _legend_entry_to_mcp(entry: Any) -> dict[str, Any]:
    """Distinguish "no label was extracted" from "the label is an empty string".

    An empty string reads to a model as a blank to fill in; both round-2 MCP agents
    filled it in with invented lithology names.
    """

    data = entry.to_dict()
    label = data.get("label")
    extracted = bool(label) and str(label).strip() != ""
    data["label"] = label if extracted else None
    data["label_extraction"] = "extracted" if extracted else "not_available"
    return data


def knowledge_bundle_to_mcp(bundle: Any) -> dict[str, Any]:
    data = bundle.to_dict() if hasattr(bundle, "to_dict") else dict(bundle)
    return redact_paths(data)


def legend_enrichment_to_mcp(enrichment: Any) -> dict[str, Any]:
    data = enrichment.to_dict() if hasattr(enrichment, "to_dict") else dict(enrichment)
    return redact_paths(data)


def serialize_georef(
    georef: Any,
    *,
    pixel_extent: list[float] | tuple[float, float, float, float],
    gcps: list[Mapping[str, float]],
    trace_id: str,
) -> dict[str, Any]:
    coefficients = [float(value) for value in georef.affine.coefficients]
    return {
        "schema_version": "georef/v1",
        "crs": georef.crs,
        "affine": {
            "coefficients": coefficients,
            "a": coefficients[0],
            "b": coefficients[1],
            "c": coefficients[2],
            "d": coefficients[3],
            "e": coefficients[4],
            "f": coefficients[5],
        },
        "bounds": georef.bounds.to_dict(),
        "residual": float(georef.residual),
        "residual_units": georef.residual_units,
        "residual_m": georef.residual_m,
        "residual_diagnostic": georef.residual_diagnostic,
        "fit_method": georef.fit_method,
        "gcp_pixel_errors": list(georef.gcp_pixel_errors),
        "holdout_error": georef.holdout_error,
        "pixel_extent": [float(value) for value in pixel_extent],
        "gcps": [dict(gcp) for gcp in gcps],
        "gcp_count": len(gcps),
        "trace_id": trace_id,
        "warnings": list(georef.warnings),
    }


def success_result(
    *,
    structured: Mapping[str, Any],
    text_summary: str,
    trace_id: str,
    content: list[dict[str, Any]] | None = None,
    resource_links: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    output = dict(structured)
    output.setdefault("schema_version", "geomap-tool-result/v1")
    output.setdefault("trace_id", trace_id)
    visible_text = append_digest(text_summary, build_digest(output))
    output["text_summary"] = visible_text
    if resource_links:
        output["resource_links"] = list(resource_links)
    result_content = [{"type": "text", "text": visible_text}]
    if content:
        result_content.extend(content)
    return {
        "content": result_content,
        "structuredContent": output,
        "isError": False,
    }


def tool_definitions() -> list[dict[str, Any]]:
    return [
        _tool(
            "geomap_list_capabilities",
            "Discover registered, installed, configured, and ready capabilities. Call this first; inspect provider readiness, supported_requests, and missing_requirements before selecting a workflow.",
            {},
            read_only=True,
            idempotent=True,
        ),
        _tool(
            "geomap_register_map",
            "Register an existing local image under an allowed root. Persists map state and returns the only supported source resource URI.",
            {"path": {"type": "string"}},
            required=("path",),
            read_only=False,
            idempotent=True,
        ),
        _tool(
            "geomap_process_image",
            "Run HIE layout and legend extraction for one registered map. Requires map_processing.ready; persists crops and processing state for later resource reads.",
            {"map_id": {"type": "string"}, "map_uri": {"type": "string"}},
            read_only=False,
            idempotent=False,
            constraints=(_exactly_one("map_id", "map_uri"),),
        ),
        _tool(
            "geomap_prepare_detectors",
            "Download and install only the manifest-approved PEACE runtime and detector weights into the server data root. Performs network access and writes to disk; confirm with the user before calling. Exposed by default; an operator may disable it.",
            {},
            read_only=False,
            idempotent=True,
        ),
        _tool(
            "geomap_prepare_knowledge",
            "Download and install only the manifest-approved PEACE knowledge asset into the server data root. Performs network access and writes to disk; confirm with the user before calling. Exposed by default; an operator may disable it.",
            {},
            read_only=False,
            idempotent=True,
        ),
        _tool(
            "geomap_georeference",
            "Fit an affine georeference from at least two client-read GCPs. Persists georef state when a map reference is supplied; inspect residual and warnings next.",
            {
                "map_id": {"type": "string"},
                "map_uri": {"type": "string"},
                "crs": {"type": ["string", "integer"]},
                "gcps": {"type": "array", "minItems": 2, "items": GCP_SCHEMA},
                "pixel_extent": {
                    "type": "array",
                    "minItems": 4,
                    "maxItems": 4,
                    "items": {"type": "number"},
                },
                "main_map_artifact_uri": {"type": "string"},
            },
            required=("crs", "gcps"),
            read_only=False,
            idempotent=False,
            constraints=(_not_both("map_id", "map_uri"),),
        ),
        _tool(
            "geomap_query_knowledge",
            "Query configured knowledge providers from explicit bounds, labels, or text. Persists a new bundle; treat warnings and provenance as evidence, including for empty results.",
            KNOWLEDGE_REQUEST_PROPERTIES,
            read_only=False,
            idempotent=False,
            constraints=(_knowledge_query_input(),),
        ),
        _tool(
            "geomap_query_map",
            "Query knowledge from registered map state or inline metadata. Requires bounds or legend labels and persists a new bundle resource.",
            {
                "map_id": {"type": "string"},
                "map_uri": {"type": "string"},
                "metadata": {"type": "object", "minProperties": 1},
                "question": {"type": "string"},
                **KNOWLEDGE_REQUEST_PROPERTIES,
            },
            read_only=False,
            idempotent=False,
            constraints=(
                _not_both("map_id", "map_uri"),
                _map_query_input(),
            ),
        ),
        _tool(
            "geomap_enrich_legend",
            "Resolve rock type and stratigraphic age for one non-empty legend label. Review provider warnings before using the result.",
            {"label": {"type": "string", "minLength": 1}},
            required=("label",),
            read_only=True,
            idempotent=True,
        ),
        _tool(
            "geomap_render_knowledge_overlay",
            "Render one bundle with inline or stored georeferencing. Writes new SVG and optional PNG resources; read returned URIs for visual evidence.",
            {
                "map_id": {"type": "string"},
                "map_uri": {"type": "string"},
                "bundle_uri": {"type": "string"},
                "bundle": KNOWLEDGE_BUNDLE_INPUT_SCHEMA,
                "georef": GEOREFERENCE_SCHEMA,
            },
            read_only=False,
            idempotent=False,
            constraints=(
                _not_both("map_id", "map_uri"),
                _exactly_one("bundle_uri", "bundle"),
                _at_least_one("map_id", "map_uri", "georef"),
            ),
        ),
    ]


BOUNDS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["min_lon", "min_lat", "max_lon", "max_lat"],
    "properties": {
        "min_lon": {"type": "number", "minimum": -180, "maximum": 180},
        "min_lat": {"type": "number", "minimum": -90, "maximum": 90},
        "max_lon": {"type": "number", "minimum": -180, "maximum": 180},
        "max_lat": {"type": "number", "minimum": -90, "maximum": 90},
        "crs": {"type": "string"},
    },
}

GCP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["pixel_x", "pixel_y", "world_x", "world_y"],
    "properties": {
        "pixel_x": {"type": "number"},
        "pixel_y": {"type": "number"},
        "world_x": {"type": "number"},
        "world_y": {"type": "number"},
    },
}

GEOREFERENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["crs", "affine", "bounds", "residual"],
    "properties": {
        "schema_version": {"const": "georef/v1"},
        "crs": {"type": "string"},
        "affine": {
            "type": "object",
            "properties": {
                "coefficients": {
                    "type": "array",
                    "minItems": 6,
                    "maxItems": 6,
                    "items": {"type": "number"},
                },
                "a": {"type": "number"},
                "b": {"type": "number"},
                "c": {"type": "number"},
                "d": {"type": "number"},
                "e": {"type": "number"},
                "f": {"type": "number"},
            },
            "anyOf": [
                {"required": ["coefficients"]},
                {"required": ["a", "b", "c", "d", "e", "f"]},
            ],
        },
        "bounds": BOUNDS_SCHEMA,
        "residual": {"type": "number"},
        "residual_units": {"type": "string"},
        "residual_m": {"type": ["number", "null"]},
        "residual_diagnostic": {"type": "boolean"},
        "fit_method": {
            "enum": [
                "axis-aligned-exact-2gcp",
                "affine-exact-3gcp",
                "affine-least-squares",
            ]
        },
        "gcp_pixel_errors": {
            "type": "array",
            "items": {"type": ["number", "null"]},
        },
        "holdout_error": {"type": ["number", "null"]},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "pixel_extent": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "items": {"type": "number"},
        },
        "gcps": {"type": "array", "items": GCP_SCHEMA},
        "gcp_count": {"type": "integer"},
    },
}

KNOWLEDGE_REQUEST_PROPERTIES: dict[str, Any] = {
    "bounds": {"anyOf": [BOUNDS_SCHEMA, {"type": "null"}]},
    "legend_labels": {"type": "array", "minItems": 1, "items": {"type": "string"}},
    "query_text": {"type": ["string", "null"], "minLength": 1},
    "include": {"type": "array", "items": {"type": "string"}},
    "exclude": {"type": "array", "items": {"type": "string"}},
    "max_records": {"type": ["integer", "null"], "minimum": 0},
    "max_records_by_provider": {
        "type": "object",
        "additionalProperties": {"type": "integer", "minimum": 0},
    },
    "provider_options": {"type": "object"},
}

KNOWLEDGE_BUNDLE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["schema_version", "items", "warnings", "provider_versions"],
    "properties": {
        "schema_version": {"const": "knowledge/v2"},
        "bounds": {"anyOf": [BOUNDS_SCHEMA, {"type": "null"}]},
        "items": {"type": "array"},
        "selected_item_ids": {"type": ["array", "null"]},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "provider_versions": {"type": "object"},
        "trace": {"type": ["object", "null"]},
    },
}

STRUCTURED_CONTENT_SCHEMA: dict[str, Any] = {
    "$schema": JSON_SCHEMA,
    "title": "GeomapStructuredContent",
    "description": "Versioned geomap tool result contract. Tool payload fields are additive within v1.",
    "type": "object",
    "required": ["schema_version", "trace_id", "text_summary"],
    "properties": {
        "schema_version": {"type": "string"},
        "trace_id": {"type": "string"},
        "text_summary": {"type": "string"},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "resource_links": {"type": "array"},
    },
    "additionalProperties": True,
}


def _tool(
    name: str,
    description: str,
    properties: Mapping[str, Any],
    *,
    required: tuple[str, ...] = (),
    read_only: bool,
    idempotent: bool,
    constraints: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    input_schema = {
        "$schema": JSON_SCHEMA,
        "type": "object",
        "properties": dict(properties),
        "required": list(required),
        "additionalProperties": False,
    }
    if constraints:
        input_schema["allOf"] = [dict(constraint) for constraint in constraints]
    return {
        "name": name,
        "description": description,
        "inputSchema": input_schema,
        "outputSchema": dict(STRUCTURED_CONTENT_SCHEMA),
        "annotations": {
            "readOnlyHint": read_only,
            "destructiveHint": False,
            "idempotentHint": idempotent,
        },
    }


def _at_least_one(*names: str) -> dict[str, Any]:
    return {"anyOf": [{"required": [name]} for name in names]}


def _knowledge_query_input() -> dict[str, Any]:
    return {
        "anyOf": [
            {"required": ["bounds"], "properties": {"bounds": {"type": "object"}}},
            {
                "required": ["legend_labels"],
                "properties": {"legend_labels": {"type": "array", "minItems": 1}},
            },
            {
                "required": ["query_text"],
                "properties": {"query_text": {"type": "string", "minLength": 1}},
            },
        ]
    }


def _map_query_input() -> dict[str, Any]:
    return {
        "anyOf": [
            {"required": ["map_id"]},
            {"required": ["map_uri"]},
            {
                "required": ["metadata"],
                "properties": {"metadata": {"type": "object", "minProperties": 1}},
            },
            {"required": ["bounds"], "properties": {"bounds": {"type": "object"}}},
            {
                "required": ["legend_labels"],
                "properties": {"legend_labels": {"type": "array", "minItems": 1}},
            },
        ]
    }


def _not_both(first: str, second: str) -> dict[str, Any]:
    return {"not": {"required": [first, second]}}


def _exactly_one(first: str, second: str) -> dict[str, Any]:
    return {
        "oneOf": [
            {"required": [first], "not": {"required": [second]}},
            {"required": [second], "not": {"required": [first]}},
        ]
    }


def _looks_like_local_path(value: str) -> bool:
    if value.startswith(("geomap://", "http://", "https://")):
        return False
    return value.startswith("/") or value.startswith("~")


__all__ = [
    "STRUCTURED_CONTENT_SCHEMA",
    "GEOREFERENCE_SCHEMA",
    "JSON_SCHEMA",
    "KNOWLEDGE_SCHEMA_VERSION",
    "MAP_PROCESSING_SCHEMA_VERSION",
    "knowledge_bundle_to_mcp",
    "legend_enrichment_to_mcp",
    "map_processing_result_to_mcp",
    "new_trace_id",
    "redact_paths",
    "serialize_georef",
    "success_result",
    "tool_definitions",
]
