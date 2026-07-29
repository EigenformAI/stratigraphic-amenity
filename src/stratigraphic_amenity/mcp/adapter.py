"""SDK-backed implementation of the geomap MCP tool surface."""

from __future__ import annotations

import functools
import importlib.util
import json
import os
import re
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Callable, Mapping

from ..knowledge import Bounds, KnowledgeBundle, KnowledgeItem, KnowledgeRequest
from ..knowledge import KnowledgeService
from ..knowledge.preparation import KnowledgePreparationError, prepare_knowledge
from ..knowledge.visualization import extract_knowledge_overlay, render_knowledge_overlay_svg
from ..asset_installer import AssetInstallError
from ..map_processing.detectors.preflight import detector_preflight
from ..map_processing.preparation import DetectorPreparationError, prepare_detectors
from .errors import McpToolError
from .images import make_inline_preview
from .resources import ResourceRegistry
from .schemas import (
    knowledge_bundle_to_mcp,
    legend_enrichment_to_mcp,
    map_processing_result_to_mcp,
    new_trace_id,
    redact_paths,
    serialize_georef,
    success_result,
)


KnowledgeServiceFactory = Callable[[], KnowledgeService]
MapServiceFactory = Callable[[], Any]

# One trace id per agent-facing tool call. Nested adapter calls (e.g. query_map
# delegating to query_knowledge) reuse the outer id so a single call has a single
# trace, and any McpToolError raised mid-call -- including trace-agnostic registry
# errors -- is stamped with it before it leaves the adapter.
_ACTIVE_TRACE: ContextVar[str | None] = ContextVar("geomap_active_trace_id", default=None)


def _active_trace_id() -> str:
    current = _ACTIVE_TRACE.get()
    return current if current is not None else new_trace_id()


def _traced(method: Callable[..., Any]) -> Callable[..., Any]:
    """Stamp the call's trace id onto any McpToolError that lacks one."""

    @functools.wraps(method)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        existing = _ACTIVE_TRACE.get()
        trace_id = existing if existing is not None else new_trace_id()
        token = _ACTIVE_TRACE.set(trace_id)
        try:
            return method(self, *args, **kwargs)
        except McpToolError as exc:
            if exc.trace_id is None:
                exc.trace_id = trace_id
            raise
        finally:
            _ACTIVE_TRACE.reset(token)

    return wrapper


class GeomapMcpAdapter:
    """Thin protocol-independent adapter over existing local SDK services."""

    def __init__(
        self,
        *,
        registry: ResourceRegistry | None = None,
        knowledge_service_factory: KnowledgeServiceFactory | None = None,
        map_service_factory: MapServiceFactory | None = None,
    ):
        self.registry = registry or ResourceRegistry.from_env()
        self._knowledge_service_factory = knowledge_service_factory or KnowledgeService.from_env
        self._map_service_factory = map_service_factory or self._default_map_service
        self._knowledge_service: KnowledgeService | None = None
        self._map_service: Any | None = None

    @_traced
    def list_capabilities(self) -> dict[str, Any]:
        trace_id = _active_trace_id()
        service = self._knowledge()
        config = self._map_config()
        providers = [
            _provider_capability(registration, getattr(service, "config", None))
            for registration in getattr(service, "_registrations", [])
        ]
        knowledge_config = getattr(service, "config", None)
        ready_provider_count = sum(1 for provider in providers if provider["ready"])
        geo_installed = _module_available("numpy") and _module_available("pyproj")
        capabilities = {
            "map_registration": _capability(
                installed=True,
                configured=bool(self.registry.allowed_roots),
                missing=[] if self.registry.allowed_roots else ["at least one allowed filesystem root"],
            ),
            "map_processing": _map_processing_capability(config),
            "detector_preparation": _detector_preparation_capability(config),
            "knowledge_preparation": _knowledge_preparation_capability(knowledge_config),
            "georeferencing": _capability(
                installed=geo_installed,
                configured=True,
                missing=[] if geo_installed else ["install the 'geo' extra"],
            ),
            "knowledge_query": _capability(
                installed=True,
                configured=ready_provider_count > 0,
                missing=(
                    []
                    if ready_provider_count > 0
                    else ["at least one ready knowledge provider"]
                ),
            ),
            "overlay_rendering": _capability(installed=True, configured=True, missing=[]),
        }
        capabilities["knowledge_query"].update(
            {
                "ready_provider_count": ready_provider_count,
                "registered_provider_count": len(providers),
            }
        )
        structured = {
            "schema_versions": {
                "map_processing": "map-processing/v1",
                "knowledge": "knowledge/v2",
                "georef": "georef/v1",
                "mcp_registry": "mcp-registry/v1",
            },
            "installed": {
                "mcp": _module_available("mcp"),
                "pillow": _module_available("PIL"),
                "cv2": _module_available("cv2"),
                "numpy": _module_available("numpy"),
                "pyproj": _module_available("pyproj"),
                "httpx": _module_available("httpx"),
                "earthengine": _module_available("ee"),
                "sentence_transformers": _module_available("sentence_transformers"),
                "torch": _module_available("torch"),
            },
            "detectors": {
                "component_model_present": config.resolved_component_model_path.exists(),
                "legend_model_present": config.resolved_legend_model_path.exists(),
                "runtime_available": capabilities["map_processing"]["installed"],
            },
            "capabilities": capabilities,
            "providers": providers,
            "allowed_roots": self.registry.allowed_root_labels(),
            "limits": self.registry.limits,
        }
        return success_result(
            structured=structured,
            text_summary=_capabilities_summary(capabilities, provider_count=len(providers)),
            trace_id=trace_id,
        )

    @_traced
    def register_map(self, path: str) -> dict[str, Any]:
        trace_id = _active_trace_id()
        path_string = str(path)
        if path_string.startswith("geomap://maps/"):
            structured = self.registry.map_public(self.registry.map_id_from_uri(path_string))
        else:
            structured = self.registry.register_map(path_string)
        return success_result(
            structured=structured,
            text_summary=f"Registered map {structured['map_id']}.",
            trace_id=trace_id,
            resource_links=[
                {
                    "uri": structured["source_uri"],
                    "name": "source map image",
                    "mimeType": structured["mime_type"],
                }
            ],
        )

    @_traced
    def process_image(self, *, map_id: str | None = None, map_uri: str | None = None) -> dict[str, Any]:
        trace_id = _active_trace_id()
        resolved_map_id = self._resolve_map_id(map_id=map_id, map_uri=map_uri)
        image_path = self.registry.source_path(resolved_map_id)
        try:
            result = self._map().process_image(image_path)
        except Exception as exc:  # noqa: BLE001 - optional detector failures need typed MCP errors.
            cause = _detector_cause(exc)
            if exc.__class__.__name__ in {"OptionalDependencyError", "DetectorLoadError"} or cause:
                raise self._detector_not_ready(exc, cause=cause, trace_id=trace_id) from exc
            raise
        # One map carries many artifacts; coalesce their registrations into a
        # single locked merge-write instead of one per artifact.
        with self.registry.deferred_save():
            structured = map_processing_result_to_mcp(
                result,
                registry=self.registry,
                map_id=resolved_map_id,
            )
            content: list[dict[str, Any]] = []
            preview = self._preview_for_role(structured.get("artifacts", []), "detection_overlay")
            if preview is not None:
                structured["preview"] = preview["metadata"]
                content.append(preview["content"])
            self.registry.set_map_processing(resolved_map_id, structured)
        resource_links = [
            {"uri": artifact["uri"], "name": artifact.get("role") or "artifact", "mimeType": artifact.get("mime_type")}
            for artifact in structured.get("artifacts", [])
        ]
        return success_result(
            structured=structured,
            text_summary=_processing_summary(
                structured, map_id=resolved_map_id, has_preview=bool(content)
            ),
            trace_id=trace_id,
            content=content,
            resource_links=resource_links,
        )

    def _detector_not_ready(
        self, exc: BaseException, *, cause: dict[str, Any], trace_id: str | None
    ) -> McpToolError:
        """Build the one error an MCP client can actually act on.

        Clients act on tool errors rather than on capability listings, and their shell is
        not the server's environment, so a bare installer command sends them to the wrong
        place. Carry the full requirement list and the remedy that works from here.
        """

        try:
            missing = list(_map_processing_capability(self._map_config())["missing_requirements"])
        except Exception:  # noqa: BLE001 - guidance must not depend on a second probe succeeding.
            missing = []
        if detector_preparation_enabled():
            hints = [
                "Call `geomap_prepare_detectors` to install the approved runtime and weights "
                "into the server's data root. Confirm with the user first: it downloads about "
                "200 MiB and writes to disk.",
            ]
        else:
            hints = [
                "Ask the server operator to run `stratigraphic-amenity-assets --all "
                '--root "$GEOMAP_DATA_ROOT"` in the server environment, or to re-expose '
                "`geomap_prepare_detectors`.",
            ]
        hints.append(
            "Do not run installer commands in your own shell. It is a different environment "
            "from the server, so its PATH may lack the command and anything it installs lands "
            "in the wrong data root."
        )
        if any("missing" in item and "module" not in item for item in missing):
            hints.append(
                "Requirements that are Python packages cannot be installed by any tool here; "
                "report those to the operator."
            )
        # Inline both the remedy and the list: a host may surface only `message`, in
        # which case pointers to details.* and recovery_hints reach nobody.
        if detector_preparation_enabled():
            remedy = (
                " Call `geomap_prepare_detectors` on this server, after confirming with the "
                "user, to install the approved runtime and weights."
            )
        else:
            remedy = (
                " Report this to the server operator. Do not run the quoted commands in your "
                "own shell; it is a different environment from the server."
            )
        outstanding = (
            " Outstanding requirements: " + "; ".join(missing) + "."
            if missing
            else " The specific requirement could not be determined."
        )
        return McpToolError(
            "missing_extra",
            "The detector is not ready in the server environment." + remedy + outstanding,
            trace_id=trace_id,
            details={
                "missing_requirements": missing,
                "detector_error": _scrub_path_tokens(str(exc)),
            },
            recovery_hints=hints,
            cause=cause,
        )

    @_traced
    def prepare_detectors(self) -> dict[str, Any]:
        trace_id = _active_trace_id()
        if not detector_preparation_enabled():
            raise McpToolError(
                "preparation_disabled",
                "Detector preparation is disabled by the server operator.",
                recovery_hints=[
                    "Ask the server operator to unset GEOMAP_MCP_ENABLE_DETECTOR_PREPARATION, "
                    "or set it to true, and restart the server. Do not install detector assets "
                    "from the client's shell; it is a different environment.",
                ],
            )
        try:
            result = prepare_detectors(self._map_config())
        except DetectorPreparationError as exc:
            raise McpToolError("detector_configuration_mismatch", str(exc)) from exc
        except AssetInstallError as exc:
            cause = _detector_cause(exc)
            raise McpToolError(
                "asset_install_failed",
                "An approved detector asset could not be installed.",
                cause=cause,
                recovery_hints=[
                    "Ask the server operator to inspect stderr using trace_id and repair or "
                    "force-reinstall the incomplete asset."
                ],
            ) from exc
        map_status = self.list_capabilities()["structuredContent"]["capabilities"]["map_processing"]
        # Assets are only one of the three requirements; claiming success while the
        # Python dependencies are still absent is what sends clients hunting.
        prepared = f"Prepared {len(result.assets)} approved detector assets."
        warnings: list[str] = []
        if map_status["ready"]:
            summary = f"{prepared} Map processing is ready."
        else:
            summary = (
                f"{prepared} Map processing is still not ready; this tool installs assets only "
                "and cannot install Python packages. See map_processing.missing_requirements."
            )
            warnings.append(
                "Detector assets were installed but map processing is not ready. The remaining "
                "requirements must be resolved by the server operator."
            )
        return success_result(
            structured={
                "assets": list(result.assets),
                "map_processing": map_status,
                "performs_network_access": True,
                "warnings": warnings,
            },
            text_summary=summary,
            trace_id=trace_id,
        )

    @_traced
    def prepare_knowledge(self) -> dict[str, Any]:
        trace_id = _active_trace_id()
        if not knowledge_preparation_enabled():
            raise McpToolError(
                "preparation_disabled",
                "Knowledge preparation is disabled by the server operator.",
                recovery_hints=[
                    "Ask the server operator to unset GEOMAP_MCP_ENABLE_KNOWLEDGE_PREPARATION, "
                    "or set it to true, and restart the server. Do not install knowledge assets "
                    "from the client's shell; it is a different environment.",
                ],
            )
        service = self._knowledge()
        config = getattr(service, "config", None)
        if config is None:
            raise McpToolError(
                "knowledge_configuration_mismatch",
                "The knowledge service does not expose a provisionable configuration.",
            )
        try:
            result = prepare_knowledge(config)
        except KnowledgePreparationError as exc:
            raise McpToolError("knowledge_configuration_mismatch", str(exc)) from exc
        except AssetInstallError as exc:
            raise McpToolError(
                "asset_install_failed",
                "The approved knowledge asset could not be installed.",
                recovery_hints=[
                    "Ask the server operator to inspect stderr using trace_id and repair or "
                    "force-reinstall the incomplete asset."
                ],
            ) from exc

        capabilities = self.list_capabilities()["structuredContent"]
        providers = capabilities["providers"]
        ready_count = sum(1 for provider in providers if provider["ready"])
        ready_ids = [provider["id"] for provider in providers if provider["ready"]]
        blocked_ids = [provider["id"] for provider in providers if not provider["ready"]]
        summary = (
            f"Prepared {len(result.assets)} approved knowledge asset(s). "
            f"{ready_count} of {len(providers)} registered provider(s) are ready. "
            f"Ready providers: {', '.join(ready_ids) or 'none'}. "
            "Retry earlier requests to ready providers."
        )
        if blocked_ids:
            summary += f" Still not ready: {', '.join(blocked_ids)}."
        warnings = []
        if ready_count < len(providers):
            warnings.append(
                "The knowledge asset was installed, but some providers still require Python "
                "packages, credentials, source mirrors, or other configuration."
            )
        return success_result(
            structured={
                "assets": list(result.assets),
                "providers": providers,
                "knowledge_query": capabilities["capabilities"]["knowledge_query"],
                "performs_network_access": True,
                "warnings": warnings,
            },
            text_summary=summary,
            trace_id=trace_id,
        )

    @_traced
    def georeference(
        self,
        *,
        crs: str | int,
        gcps: list[Mapping[str, Any] | list[float] | tuple[float, float, float, float]],
        pixel_extent: list[float] | tuple[float, float, float, float] | None = None,
        map_id: str | None = None,
        map_uri: str | None = None,
        main_map_artifact_uri: str | None = None,
    ) -> dict[str, Any]:
        trace_id = _active_trace_id()
        resolved_map_id = self._resolve_map_id(map_id=map_id, map_uri=map_uri, required=False)
        normalized_gcps = [_gcp_dict(gcp) for gcp in gcps]
        if pixel_extent is None and main_map_artifact_uri:
            entry = self.registry.artifact_entry(main_map_artifact_uri)
            bbox = entry.get("bbox")
            if bbox:
                pixel_extent = [float(value) for value in bbox]
        if pixel_extent is None and resolved_map_id:
            pixel_extent = self._main_map_pixel_extent(resolved_map_id)
        if pixel_extent is None:
            raise McpToolError("invalid_bounds", "pixel_extent or main map artifact bbox is required.")
        try:
            from ..georef import GroundControlPoint, georeference_bounds
        except Exception as exc:  # noqa: BLE001 - missing geo extra surfaces as typed error.
            raise McpToolError("missing_extra", "Install the 'geo' extra for georeferencing.") from exc
        try:
            ref = georeference_bounds(
                crs=crs,
                gcps=[GroundControlPoint(**gcp) for gcp in normalized_gcps],
                pixel_extent=tuple(float(value) for value in pixel_extent),
            )
        except Exception as exc:  # noqa: BLE001
            if exc.__class__.__name__ == "GeoReferenceError" and "install" in str(exc).lower():
                raise McpToolError("missing_extra", str(exc), trace_id=trace_id) from exc
            raise McpToolError("invalid_bounds", str(exc), trace_id=trace_id) from exc
        structured = serialize_georef(
            ref,
            pixel_extent=list(pixel_extent),
            gcps=normalized_gcps,
            trace_id=trace_id,
        )
        resource_links: list[dict[str, Any]] = []
        if resolved_map_id:
            resource = self.registry.set_map_georef(resolved_map_id, structured)
            structured["georef_uri"] = resource["uri"]
            resource_links.append(
                {"uri": resource["uri"], "name": "georef JSON", "mimeType": "application/json"}
            )
        return success_result(
            structured=structured,
            text_summary=(
                f"Georeferenced map bounds: lon "
                f"[{structured['bounds']['min_lon']:.4f}, {structured['bounds']['max_lon']:.4f}], "
                f"lat [{structured['bounds']['min_lat']:.4f}, {structured['bounds']['max_lat']:.4f}]."
            ),
            trace_id=trace_id,
            resource_links=resource_links,
        )

    @_traced
    def query_knowledge(
        self,
        *,
        bounds: Mapping[str, Any] | Bounds | None = None,
        legend_labels: list[str] | tuple[str, ...] | None = None,
        query_text: str | None = None,
        include: list[str] | tuple[str, ...] | None = None,
        exclude: list[str] | tuple[str, ...] | None = None,
        max_records: int | None = None,
        max_records_by_provider: Mapping[str, int] | None = None,
        provider_options: Mapping[str, Mapping[str, Any]] | None = None,
        map_id: str | None = None,
    ) -> dict[str, Any]:
        trace_id = _active_trace_id()
        try:
            request = KnowledgeRequest(
                bounds=_bounds_from_any(bounds),
                legend_labels=list(legend_labels or []),
                query_text=query_text,
                include=tuple(include or ()),
                exclude=tuple(exclude or ()),
                max_records=max_records,
                max_records_by_provider=dict(max_records_by_provider or {}),
                provider_options={key: dict(value) for key, value in (provider_options or {}).items()},
                trace_id=trace_id,
            )
        except Exception as exc:  # noqa: BLE001
            if exc.__class__.__name__ == "InvalidBoundsError":
                raise McpToolError("invalid_bounds", str(exc), trace_id=trace_id) from exc
            raise
        try:
            bundle = self._knowledge().query(request)
        except Exception as exc:  # noqa: BLE001
            if exc.__class__.__name__ in {"ProviderError", "ProviderOptionError"}:
                raise McpToolError("unknown_provider", str(exc), trace_id=trace_id) from exc
            if exc.__class__.__name__ in {"MissingAssetError", "OptionalDependencyError"}:
                raise self._knowledge_not_ready(exc, trace_id=trace_id) from exc
            raise
        return self._bundle_result(bundle, trace_id=trace_id, map_id=map_id)

    @_traced
    def query_map(
        self,
        *,
        map_id: str | None = None,
        map_uri: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        question: str | None = None,
        include: list[str] | tuple[str, ...] | None = None,
        exclude: list[str] | tuple[str, ...] | None = None,
        max_records: int | None = None,
        max_records_by_provider: Mapping[str, int] | None = None,
        provider_options: Mapping[str, Mapping[str, Any]] | None = None,
        bounds: Mapping[str, Any] | Bounds | None = None,
        legend_labels: list[str] | tuple[str, ...] | None = None,
        query_text: str | None = None,
    ) -> dict[str, Any]:
        resolved_map_id = self._resolve_map_id(map_id=map_id, map_uri=map_uri, required=False)
        metadata = dict(metadata or {})
        if bounds is None:
            bounds = metadata.get("bounds")
        labels = list(legend_labels or []) or _legend_labels_from_metadata(metadata)
        if resolved_map_id:
            processing = self.registry.get_map_processing(resolved_map_id) or {}
            labels = labels or _legend_labels_from_metadata(processing)
            if bounds is None:
                georef = self.registry.get_map_georef(resolved_map_id)
                if georef is not None:
                    bounds = georef.get("bounds")
        if bounds is None and not labels:
            raise McpToolError(
                "georef_required",
                "query_map needs stored georef bounds, explicit bounds, or legend labels.",
            )
        return self.query_knowledge(
            bounds=bounds,
            legend_labels=labels,
            query_text=query_text or question,
            include=include,
            exclude=exclude,
            max_records=max_records,
            max_records_by_provider=max_records_by_provider,
            provider_options=provider_options,
            map_id=resolved_map_id,
        )

    @_traced
    def enrich_legend(self, label: str) -> dict[str, Any]:
        trace_id = _active_trace_id()
        try:
            enrichment = self._knowledge().enrich_legend_label(label)
        except Exception as exc:  # noqa: BLE001 - optional knowledge failures need typed errors.
            if exc.__class__.__name__ in {"MissingAssetError", "OptionalDependencyError"}:
                raise self._knowledge_not_ready(exc, trace_id=trace_id) from exc
            raise
        structured = legend_enrichment_to_mcp(enrichment)
        return success_result(
            structured=structured,
            text_summary=f"Enriched legend label {label!r}.",
            trace_id=trace_id,
        )

    @_traced
    def render_knowledge_overlay(
        self,
        *,
        map_id: str | None = None,
        map_uri: str | None = None,
        bundle_uri: str | None = None,
        bundle: Mapping[str, Any] | None = None,
        georef: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        trace_id = _active_trace_id()
        resolved_map_id = self._resolve_map_id(map_id=map_id, map_uri=map_uri, required=False)
        bundle_data = self._bundle_data(bundle_uri=bundle_uri, bundle=bundle)
        georef_data = dict(georef or {})
        if not georef_data and resolved_map_id:
            georef_data = self.registry.get_map_georef(resolved_map_id) or {}
        if not georef_data:
            raise McpToolError(
                "georef_required",
                "A stored or inline georef is required to render a map-backed overlay.",
                trace_id=trace_id,
            )
        knowledge_bundle = _bundle_from_dict(bundle_data)
        metadata: dict[str, Any] = {"georef": georef_data}
        if resolved_map_id:
            metadata["image_path"] = str(self.registry.source_path(resolved_map_id))
        overlay = extract_knowledge_overlay(knowledge_bundle, metadata=metadata)
        output_dir = self.registry.cache_root / "mcp" / "v1" / "overlays"
        output_dir.mkdir(parents=True, exist_ok=True)
        stem = new_trace_id()
        svg_path = output_dir / f"{stem}.svg"
        render_knowledge_overlay_svg(overlay, svg_path)
        resources = [self.registry.register_overlay(svg_path, map_id=resolved_map_id)]
        warnings = list(overlay.warnings)
        png_preview = None
        try:
            from ..knowledge.visualization import render_knowledge_overlay_on_image

            georef_object = _georef_from_dict(georef_data)
            if resolved_map_id:
                png_path = output_dir / f"{stem}.png"
                render_knowledge_overlay_on_image(
                    overlay,
                    georef_object,
                    self.registry.source_path(resolved_map_id),
                    png_path,
                )
                png_resource = self.registry.register_overlay(png_path, map_id=resolved_map_id)
                resources.append(png_resource)
                png_preview = make_inline_preview(png_path, artifact_uri=png_resource["uri"])
        except Exception as exc:  # noqa: BLE001 - SVG remains useful when raster deps are absent.
            warnings.append(f"annotated PNG unavailable: {type(exc).__name__}: {exc}")
        structured = {
            "overlay": redact_paths(overlay.to_dict()),
            "resources": resources,
            "warnings": warnings,
        }
        content = [png_preview["content"]] if png_preview else None
        if png_preview:
            structured["preview"] = png_preview["metadata"]
        return success_result(
            structured=structured,
            text_summary=f"Rendered knowledge overlay with {len(overlay.items)} annotation item(s).",
            trace_id=trace_id,
            content=content,
            resource_links=[
                {"uri": item["uri"], "name": "knowledge overlay", "mimeType": item["mime_type"]}
                for item in resources
            ],
        )

    def read_resource(self, uri: str) -> dict[str, Any]:
        return self.registry.read_resource(uri)

    def _bundle_result(
        self,
        bundle: Any,
        *,
        trace_id: str,
        map_id: str | None = None,
    ) -> dict[str, Any]:
        structured = knowledge_bundle_to_mcp(bundle)
        structured["warnings"] = [
            _scrub_path_tokens(str(warning)) for warning in structured.get("warnings", [])
        ]
        structured["warnings"].extend(_knowledge_notice_warnings(structured.get("trace")))
        bundle_resource = self.registry.register_bundle(structured, map_id=map_id)
        structured["bundle_uri"] = bundle_resource["uri"]

        # Each item is a per-provider *summary*; the records it found live in
        # `record_count` (found) and `value` (returned). Summarizing by item
        # count hides the yield -- e.g. "1 item" for 86 mineral occurrences --
        # so surface record totals plus a per-provider breakdown an agent can
        # branch on without re-summing `item.value` itself.
        record_counts: dict[str, int] = {}
        returned_counts: dict[str, int] = {}
        truncated = False
        for item in structured.get("items", []):
            provider = item.get("provider", "unknown")
            returned = _returned_count(item.get("value"))
            found = item.get("record_count")
            found = int(found) if found is not None else returned
            record_counts[provider] = record_counts.get(provider, 0) + found
            returned_counts[provider] = returned_counts.get(provider, 0) + returned
            truncated = truncated or bool(item.get("truncated")) or found > returned

        total_found = sum(record_counts.values())
        total_returned = sum(returned_counts.values())
        structured["record_counts"] = record_counts
        structured["total_records_found"] = total_found
        structured["total_records_returned"] = total_returned
        structured["truncated"] = truncated

        summary = (
            f"Knowledge query found {total_found} record(s) "
            f"across {len(record_counts)} provider(s)"
        )
        if total_returned < total_found:
            summary += f" ({total_returned} returned, truncated)"
        nonempty = {provider: count for provider, count in record_counts.items() if count}
        if nonempty:
            breakdown = ", ".join(f"{provider}={count}" for provider, count in nonempty.items())
            summary += f": {breakdown}."
        else:
            summary += "; no provider returned records."
        warnings = list(structured.get("warnings", []))
        if warnings:
            summary += f" {len(warnings)} warning(s): " + " | ".join(warnings)
        return success_result(
            structured=structured,
            text_summary=summary,
            trace_id=trace_id,
            resource_links=[
                {"uri": bundle_resource["uri"], "name": "knowledge bundle", "mimeType": "application/json"}
            ],
        )

    def _knowledge_not_ready(self, exc: BaseException, *, trace_id: str) -> McpToolError:
        scrubbed = _scrub_path_tokens(str(exc))
        if exc.__class__.__name__ == "MissingAssetError":
            if knowledge_preparation_enabled():
                remedy = (
                    "Call `geomap_prepare_knowledge` on this server after confirming with the "
                    "user; it downloads approved assets and writes to disk."
                )
            else:
                remedy = (
                    "Ask the server operator to install `peace-knowledge-base` in the server "
                    "environment or re-expose the knowledge preparation tool."
                )
            return McpToolError(
                "missing_knowledge_asset",
                f"A required knowledge asset is unavailable on the server. {remedy}",
                trace_id=trace_id,
                details={"knowledge_error": scrubbed},
                recovery_hints=[
                    remedy,
                    "Do not run installer commands in the client shell; it is a different "
                    "environment from the server.",
                ],
            )
        remedy = (
            "Ask the server operator to install the required Python extra in the server "
            "environment; knowledge preparation installs assets only."
        )
        return McpToolError(
            "missing_extra",
            f"A knowledge provider dependency is unavailable on the server. {remedy}",
            trace_id=trace_id,
            details={"knowledge_error": scrubbed},
            recovery_hints=[remedy],
        )

    def _preview_for_role(self, artifacts: list[Mapping[str, Any]], role: str) -> dict[str, Any] | None:
        for artifact in artifacts:
            if artifact.get("role") != role:
                continue
            try:
                entry = self.registry.artifact_entry(str(artifact["uri"]))
            except McpToolError:
                return None
            return make_inline_preview(entry["path"], artifact_uri=str(artifact["uri"]))
        return None

    def _resolve_map_id(
        self,
        *,
        map_id: str | None,
        map_uri: str | None,
        required: bool = True,
    ) -> str | None:
        if map_id:
            self.registry.map_public(map_id)
            return map_id
        if map_uri:
            return self.registry.map_id_from_uri(map_uri)
        if required:
            raise McpToolError("artifact_not_found", "map_id or map_uri is required.")
        return None

    def _main_map_pixel_extent(self, map_id: str) -> list[float] | None:
        processing = self.registry.get_map_processing(map_id) or {}
        for detection in processing.get("regions", {}).get("main_map", []):
            bbox = detection.get("bbox")
            if bbox:
                return [float(value) for value in bbox]
        return None

    def _bundle_data(
        self,
        *,
        bundle_uri: str | None,
        bundle: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if bundle is not None:
            return redact_paths(dict(bundle))
        if bundle_uri is None:
            raise McpToolError("artifact_not_found", "bundle_uri or inline bundle is required.")
        content = self.registry.read_resource(bundle_uri)
        if "text" not in content:
            raise McpToolError("unsupported_media", "Bundle resource must be JSON text.")
        return json.loads(content["text"])

    def _knowledge(self) -> KnowledgeService:
        if self._knowledge_service is None:
            self._knowledge_service = self._knowledge_service_factory()
        return self._knowledge_service

    def _map(self) -> Any:
        if self._map_service is None:
            self._map_service = self._map_service_factory()
        return self._map_service

    @staticmethod
    def _default_map_service() -> Any:
        from ..map_processing import MapProcessingService

        return MapProcessingService()

    @staticmethod
    def _map_config() -> Any:
        from ..map_processing.config import MapProcessingConfig

        return MapProcessingConfig.from_env()


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _managed_runtime_present(root: Any) -> bool:
    runtime = Path(root)
    init_path = runtime / "__init__.py"
    model_path = runtime / "models" / "yolov10" / "model.py"
    if not init_path.is_file() or not model_path.is_file():
        return False
    try:
        return "os.sys.path.append" not in init_path.read_text(encoding="utf-8")
    except OSError:
        return False


def _capability(
    *, installed: bool, configured: bool, missing: list[str], registered: bool = True
) -> dict[str, Any]:
    return {
        "registered": registered,
        "installed": bool(installed),
        "configured": bool(configured),
        "ready": bool(installed and configured and not missing),
        "missing_requirements": list(missing),
    }


def detector_preparation_enabled() -> bool:
    """Detector provisioning is exposed unless an operator explicitly opts out.

    Blank or unset keeps the default. Any other value must be recognizably truthy,
    so a typo in the locking direction fails closed rather than re-exposing the tool.
    """

    configured = os.getenv("GEOMAP_MCP_ENABLE_DETECTOR_PREPARATION", "").strip().lower()
    if not configured:
        return True
    return configured in {"1", "true", "yes", "y", "on"}


def knowledge_preparation_enabled() -> bool:
    """Knowledge provisioning is exposed unless an operator explicitly opts out."""

    configured = os.getenv("GEOMAP_MCP_ENABLE_KNOWLEDGE_PREPARATION", "").strip().lower()
    if not configured:
        return True
    return configured in {"1", "true", "yes", "y", "on"}


def _capabilities_summary(capabilities: Mapping[str, Any], *, provider_count: int) -> str:
    """State readiness in text.

    Round-2 agents all called this tool first and then ignored it, because a host that
    surfaces only text showed them a provider count and nothing about what was ready.
    """

    not_ready = [name for name, entry in capabilities.items() if not entry.get("ready")]
    knowledge = capabilities.get("knowledge_query", {})
    ready_provider_count = int(knowledge.get("ready_provider_count", 0))
    registered_provider_count = int(
        knowledge.get("registered_provider_count", provider_count)
    )
    parts = [
        f"{ready_provider_count} of {registered_provider_count} knowledge providers are ready."
    ]
    if not not_ready:
        if ready_provider_count == registered_provider_count:
            parts.append("All capabilities are ready.")
        else:
            parts.append(
                "Knowledge support is partial; inspect each provider's ready status and "
                "supported_requests before querying."
            )
        return " ".join(parts)
    described = ", ".join(
        f"{name} ({len(capabilities[name].get('missing_requirements', []))} outstanding)"
        for name in sorted(not_ready)
    )
    parts.append(f"Not ready: {described}.")
    processing = capabilities.get("map_processing", {})
    if not processing.get("ready"):
        remedy = (
            " Call `geomap_prepare_detectors` first."
            if capabilities.get("detector_preparation", {}).get("ready")
            else " Ask the server operator to resolve them."
        )
        parts.append(
            "Do not call `geomap_process_image` until map_processing is ready." + remedy
        )
    if not knowledge.get("ready"):
        remedy = (
            " Call `geomap_prepare_knowledge` first."
            if capabilities.get("knowledge_preparation", {}).get("ready")
            else " Ask the server operator to resolve them."
        )
        parts.append("Do not query knowledge until at least one provider is ready." + remedy)
    elif ready_provider_count < registered_provider_count:
        parts.append(
            "Knowledge support is partial; inspect each provider's ready status and "
            "supported_requests before querying."
        )
    return " ".join(parts)


def _processing_summary(structured: Mapping[str, Any], *, map_id: str, has_preview: bool) -> str:
    """Summarize a processing result for hosts that surface only text.

    A client may show the model this string and the attached preview image while never
    surfacing structuredContent. The two things a model reliably gets wrong from a
    picture alone -- inventing legend labels and measuring boxes on the preview -- are
    therefore stated here rather than only in structured fields.
    """

    legend = list(structured.get("legend", []))
    size = structured.get("size", {})
    width, height = size.get("width"), size.get("height")
    regions = sum(len(items) for items in structured.get("regions", {}).values())
    parts = [
        f"Processed map {map_id}: {regions} regions, {len(legend)} legend entries. "
        f"All boxes are in the {width}x{height} source frame."
    ]
    unlabeled = [
        entry for entry in legend if entry.get("label_extraction") != "extracted"
    ]
    if unlabeled:
        parts.append(
            f"{len(unlabeled)} of {len(legend)} legend entries have no extracted label because "
            "this build has no OCR. Report those entries as unlabeled; do not infer lithology "
            "names from the map image."
        )
    if has_preview:
        parts.append(
            "The attached preview image is downsampled and is a different coordinate frame; "
            "do not measure coordinates on it."
        )
    return " ".join(parts)


def _map_processing_capability(config: Any) -> dict[str, Any]:
    """Detector readiness, shared by the capability listing and the failure envelope.

    The error path must not depend on the rest of the capability aggregation, which
    also probes knowledge providers and can fail for unrelated reasons.
    """

    component_model = config.resolved_component_model_path.exists()
    legend_model = config.resolved_legend_model_path.exists()
    detector_runtime = _managed_runtime_present(config.resolved_ultralytics_root)
    detector_failures = detector_preflight(config.resolved_ultralytics_root)
    missing: list[str] = []
    if not detector_runtime:
        missing.append(
            "managed PEACE YOLOv10 runtime; run "
            "`stratigraphic-amenity-assets peace-yolov10-runtime "
            '--root "$GEOMAP_DATA_ROOT"` in the server environment'
        )
    missing.extend(detector_failures)
    if not component_model:
        missing.append(
            "component detector weights; run "
            "`stratigraphic-amenity-assets peace-layout-detectors "
            '--root "$GEOMAP_DATA_ROOT"` in the server environment'
        )
    if not legend_model:
        missing.append(
            "legend detector weights; run "
            "`stratigraphic-amenity-assets peace-layout-detectors "
            '--root "$GEOMAP_DATA_ROOT"` in the server environment'
        )
    return _capability(
        installed=detector_runtime and not detector_failures,
        configured=component_model and legend_model,
        missing=missing,
    )


def _detector_preparation_capability(config: Any) -> dict[str, Any]:
    enabled = detector_preparation_enabled()
    expected_models = config.data_root / "assets" / "models"
    expected_runtime = config.data_root / "assets" / "runtime" / "ultralytics"
    configured = (
        config.model_root.resolve() == expected_models.resolve()
        and config.resolved_ultralytics_root.resolve() == expected_runtime.resolve()
    )
    installed = _module_available("gdown")
    missing = []
    if not enabled:
        missing.append(
            "detector preparation was disabled by the server operator; unset "
            "GEOMAP_MCP_ENABLE_DETECTOR_PREPARATION to restore the default"
        )
    if not installed:
        missing.append("install the 'assets' extra in the server environment")
    if not configured:
        missing.append("detector paths must use the GEOMAP_DATA_ROOT manifest destinations")
    return _capability(
        registered=enabled,
        installed=installed,
        configured=configured,
        missing=missing,
    )


def _knowledge_preparation_capability(config: Any | None) -> dict[str, Any]:
    enabled = knowledge_preparation_enabled()
    expected_root = config.data_root / "assets" / "knowledge" if config is not None else None
    configured = bool(
        config is not None
        and Path(config.knowledge_root).resolve() == Path(expected_root).resolve()
    )
    installed = _module_available("gdown")
    missing = []
    if not enabled:
        missing.append(
            "knowledge preparation was disabled by the server operator; unset "
            "GEOMAP_MCP_ENABLE_KNOWLEDGE_PREPARATION to restore the default"
        )
    if not installed:
        missing.append("install the 'assets' extra in the server environment")
    if not configured:
        missing.append("knowledge paths must use the GEOMAP_DATA_ROOT manifest destinations")
    return _capability(
        registered=enabled,
        installed=installed,
        configured=configured,
        missing=missing,
    )


# Absolute path tokens embedded mid-sentence survive redact_paths, which only replaces
# whole values. Anchor on a separator not preceded by ':', '/', or a word character so
# that geomap:// URIs and relative words are left intact.
_PATH_TOKEN = re.compile(r"(?<![:\w/\\])(?:[A-Za-z]:)?[/\\][^\s'\"`,;)]+")


def _scrub_path_tokens(text: str) -> str:
    return _PATH_TOKEN.sub("<redacted>", text)


def _knowledge_notice_warnings(trace: Any) -> list[str]:
    if not isinstance(trace, Mapping):
        return []
    events = trace.get("providers", [])
    missing_assets = sorted(
        str(event.get("provider"))
        for event in events
        if isinstance(event, Mapping)
        and event.get("provider")
        and event.get("status") == "unavailable"
        and event.get("reason") == "missing_asset"
    )
    missing_dependencies = sorted(
        str(event.get("provider"))
        for event in events
        if isinstance(event, Mapping)
        and event.get("provider")
        and event.get("status") == "unavailable"
        and event.get("reason") == "optional_dependency"
    )
    warnings: list[str] = []
    if missing_assets:
        providers = ", ".join(missing_assets)
        if knowledge_preparation_enabled():
            remedy = (
                "Call `geomap_prepare_knowledge` on this server after confirming with the user."
            )
        else:
            remedy = "Ask the server operator to install the required knowledge assets."
        warnings.append(f"Knowledge assets are unavailable for: {providers}. {remedy}")
    if missing_dependencies:
        providers = ", ".join(missing_dependencies)
        warnings.append(
            f"Optional dependencies are unavailable for: {providers}. Ask the server operator "
            "to install the required Python extras in the server environment."
        )
    for notice in trace.get("providers_not_consulted", []):
        if not isinstance(notice, Mapping) or notice.get("reason") != "disabled_by_default":
            continue
        provider = str(notice.get("provider", "unknown"))
        warnings.append(
            f"Compatible provider {provider!r} was not consulted because it is disabled by "
            f'default. Retry with include=["{provider}"].'
        )
    return warnings


def _detector_cause(exc: BaseException) -> dict[str, Any]:
    current: BaseException | None = exc
    seen = set()
    for _ in range(5):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        if isinstance(current, ModuleNotFoundError) and current.name:
            return {"type": "missing_python_module", "module": current.name}
        match = re.search(r"([A-Za-z0-9_.+-]+\.so(?:\.\d+)*)", str(current))
        if match:
            return {"type": "missing_shared_library", "library": match.group(1)}
        current = current.__cause__ or current.__context__
    return {}


def _provider_capability(registration: Any, config: Any | None) -> dict[str, Any]:
    installed = True
    configured = True
    missing: list[str] = []
    provider_id = str(registration.id)

    path_attributes = {
        "rock_type": "resolved_k2_rock_type_path",
        "rock_age": "resolved_k2_rock_age_path",
        "rock_knowledge": "resolved_k2_rock_detail_path",
        "component_usage_knowledge": "resolved_k2_usage_path",
        "downstream_task_knowledge": "resolved_k2_expertise_path",
    }
    if provider_id in path_attributes and config is not None:
        configured = getattr(config, path_attributes[provider_id]).exists()
        if not configured:
            missing.append(_knowledge_asset_remedy("PEACE knowledge base"))
        if provider_id in {
            "rock_knowledge",
            "component_usage_knowledge",
            "downstream_task_knowledge",
        }:
            installed = _module_available("sentence_transformers")
            if not installed:
                missing.append("install the 'knowledge-semantic' extra")
    elif provider_id == "earthquake_history" and config is not None:
        configured = config.resolved_earthquake_csv_path.exists() or _source_mirror_present(
            config.knowledge_sources_root, "usgs_fdsn_events"
        )
        if not configured:
            missing.append(
                _knowledge_asset_remedy("USGS earthquake data") + " or sync a source mirror"
            )
    elif provider_id == "active_faults" and config is not None:
        configured = config.resolved_active_fault_geojson_path.exists() or _source_mirror_present(
            config.knowledge_sources_root, "gem_global_active_faults"
        )
        if not configured:
            missing.append(
                _knowledge_asset_remedy("GEM active-fault data") + " or sync a source mirror"
            )
    elif provider_id in {"landcover_distribution", "population_density"}:
        installed = _module_available("ee")
        configured = bool(getattr(config, "earthengine_project", None))
        if not installed:
            missing.append("install the 'knowledge-earthengine' extra")
        if not configured:
            missing.append("GEOMAP_EARTHENGINE_PROJECT")
    elif provider_id == "mineral_occurrences":
        installed = _module_available("httpx")
        if not installed:
            missing.append("install the 'knowledge-network' extra")

    return {
        "id": provider_id,
        "name": registration.name,
        "output_keys": list(registration.output_keys),
        "supported_requests": list(getattr(registration, "supported_requests", ())),
        "default_enabled": bool(registration.default_enabled),
        "registered": True,
        "installed": installed,
        "configured": configured,
        "ready": bool(installed and configured and not missing),
        "missing_requirements": missing,
    }


def _knowledge_asset_remedy(requirement: str) -> str:
    if knowledge_preparation_enabled():
        return f"{requirement}; call `geomap_prepare_knowledge` with user confirmation"
    return (
        f"{requirement}; ask the server operator to install `peace-knowledge-base` "
        "in the server environment"
    )


def _source_mirror_present(root: Any, source_id: str) -> bool:
    if root is None:
        return False
    source_root = Path(root) / source_id
    return source_root.is_dir() and any(source_root.glob("*/manifest.json"))


def _returned_count(value: Any) -> int:
    """How many records a knowledge item actually carries in its ``value``."""

    if value is None:
        return 0
    if isinstance(value, (list, tuple)):
        return len(value)
    if isinstance(value, dict):
        return 1 if value else 0
    return 1


def _bounds_from_any(value: Mapping[str, Any] | Bounds | None) -> Bounds | None:
    if value is None:
        return None
    if isinstance(value, Bounds):
        return value
    return Bounds(**dict(value))


def _gcp_dict(value: Mapping[str, Any] | list[float] | tuple[float, float, float, float]) -> dict[str, float]:
    if isinstance(value, Mapping):
        return {
            "pixel_x": float(value["pixel_x"]),
            "pixel_y": float(value["pixel_y"]),
            "world_x": float(value["world_x"]),
            "world_y": float(value["world_y"]),
        }
    pixel_x, pixel_y, world_x, world_y = value
    return {
        "pixel_x": float(pixel_x),
        "pixel_y": float(pixel_y),
        "world_x": float(world_x),
        "world_y": float(world_y),
    }


def _legend_labels_from_metadata(metadata: Mapping[str, Any]) -> list[str]:
    explicit = metadata.get("legend_labels")
    if explicit:
        return [str(label) for label in explicit if str(label).strip()]
    labels: list[str] = []
    for entry in metadata.get("legend", []) or []:
        text: Any = None
        if isinstance(entry, Mapping):
            text = entry.get("label") or entry.get("text")
        elif isinstance(entry, (list, tuple)) and len(entry) == 2 and isinstance(entry[1], Mapping):
            text = entry[1].get("text") or entry[1].get("label")
        if text and str(text).strip():
            labels.append(str(text))
    return labels


def _bundle_from_dict(data: Mapping[str, Any]) -> KnowledgeBundle:
    bounds = _bounds_from_any(data.get("bounds"))
    items = [KnowledgeItem.from_dict(dict(item)) for item in data.get("items", [])]
    return KnowledgeBundle(
        bounds=bounds,
        items=items,
        selected_item_ids=data.get("selected_item_ids"),
        warnings=list(data.get("warnings", [])),
        provider_versions=dict(data.get("provider_versions", {})),
        trace=data.get("trace"),
        schema_version=str(data.get("schema_version", "knowledge/v2")),
    )


def _georef_from_dict(data: Mapping[str, Any]) -> Any:
    from ..georef import AffineTransform, GeoReference

    coefficients = data.get("affine", {}).get("coefficients")
    if not coefficients:
        coefficients = [data["affine"][key] for key in ("a", "b", "c", "d", "e", "f")]
    affine = AffineTransform(*[float(value) for value in coefficients], residual=float(data["residual"]))
    return GeoReference(
        crs=str(data["crs"]),
        affine=affine,
        bounds=Bounds(**data["bounds"]),
        residual=float(data["residual"]),
    )


__all__ = ["GeomapMcpAdapter"]
