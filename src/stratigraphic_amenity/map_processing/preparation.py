"""Operator-authorized provisioning for the PEACE detector assets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..asset_installer import InstallResult, provision_assets
from .config import MapProcessingConfig


DETECTOR_ASSET_IDS = ("peace-yolov10-runtime", "peace-layout-detectors")
Provision = Callable[..., list[InstallResult]]


class DetectorPreparationError(RuntimeError):
    """Configured detector paths cannot be provisioned safely."""


@dataclass(frozen=True)
class DetectorPreparationResult:
    assets: tuple[dict[str, str], ...]


def prepare_detectors(
    config: MapProcessingConfig,
    *,
    provision: Provision = provision_assets,
) -> DetectorPreparationResult:
    """Install only the manifest-pinned detector assets at the configured data root."""

    expected_model_root = config.data_root / "assets" / "models"
    expected_runtime_root = config.data_root / "assets" / "runtime" / "ultralytics"
    if (
        config.model_root.resolve() != expected_model_root.resolve()
        or config.resolved_ultralytics_root.resolve() != expected_runtime_root.resolve()
    ):
        raise DetectorPreparationError(
            "Configured detector paths do not match the approved manifest destinations."
        )
    results = provision(DETECTOR_ASSET_IDS, root=config.data_root, force=False)
    return DetectorPreparationResult(
        assets=tuple(
            {"asset_id": result.asset_id, "status": result.status} for result in results
        )
    )


__all__ = [
    "DETECTOR_ASSET_IDS",
    "DetectorPreparationError",
    "DetectorPreparationResult",
    "prepare_detectors",
]
