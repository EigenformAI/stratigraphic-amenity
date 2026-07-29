"""Operator-authorized provisioning for the approved knowledge asset."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..asset_installer import InstallResult, provision_assets
from .config import KnowledgeConfig


KNOWLEDGE_ASSET_IDS = ("peace-knowledge-base",)
Provision = Callable[..., list[InstallResult]]


class KnowledgePreparationError(RuntimeError):
    """Configured knowledge paths cannot be provisioned safely."""


@dataclass(frozen=True)
class KnowledgePreparationResult:
    assets: tuple[dict[str, str], ...]


def prepare_knowledge(
    config: KnowledgeConfig,
    *,
    provision: Provision = provision_assets,
) -> KnowledgePreparationResult:
    """Install only the manifest-pinned knowledge asset at the configured data root."""

    expected_root = config.data_root / "assets" / "knowledge"
    expected_paths = {
        "knowledge_root": expected_root,
        "resolved_earthquake_csv_path": expected_root / "earthquake_1970_4.5mag.csv",
        "resolved_active_fault_geojson_path": expected_root / "gem_active_faults_harmonized.geojson",
        "resolved_k2_rock_type_path": expected_root / "k2_rock_type.json",
        "resolved_k2_rock_age_path": expected_root / "k2_rock_age.json",
        "resolved_k2_rock_detail_path": expected_root / "k2_rock_detail.json",
        "resolved_k2_usage_path": expected_root / "k2_usage.json",
        "resolved_k2_expertise_path": expected_root / "k2_expertise.json",
    }
    if any(
        getattr(config, attribute).resolve() != expected.resolve()
        for attribute, expected in expected_paths.items()
    ):
        raise KnowledgePreparationError(
            "Configured knowledge paths do not match the approved manifest destinations."
        )

    results = provision(KNOWLEDGE_ASSET_IDS, root=config.data_root, force=False)
    return KnowledgePreparationResult(
        assets=tuple(
            {"asset_id": result.asset_id, "status": result.status} for result in results
        )
    )


__all__ = [
    "KNOWLEDGE_ASSET_IDS",
    "KnowledgePreparationError",
    "KnowledgePreparationResult",
    "prepare_knowledge",
]
