import json
from pathlib import Path

import pytest

from stratigraphic_amenity.knowledge import Bounds
from stratigraphic_amenity.knowledge.errors import (
    OptionalDependencyError,
    SourceRegistryError,
    SourceManifestError,
    SourceQueryError,
)
from stratigraphic_amenity.knowledge.sources.diss_faults import DissSeismogenicSourceAdapter
from stratigraphic_amenity.knowledge.sources.sigeom_minerals import (
    SigeomMineralOccurrenceAdapter,
    normalize_sigeom_features,
)
from stratigraphic_amenity.knowledge.sources.gem_faults import GemActiveFaultSourceAdapter
from stratigraphic_amenity.knowledge.sources.manifest import SourceManifest, find_latest_manifest
from stratigraphic_amenity.knowledge.sources.registry import default_source_registry
from stratigraphic_amenity.knowledge.sources.usgs_events import (
    EMSC_DEFAULT_PROFILE,
    EMSC_EVENT_BASE_URL,
    FdsnEventSourceAdapter,
    UsgsFdsnEventAdapter,
    normalize_geojson_events,
)


FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"


def test_source_manifest_round_trips_and_hash_ignores_retrieval_time():
    manifest = SourceManifest(
        source_id="usgs_fdsn_events",
        family="earthquake_events",
        retrieved_at="2026-06-25T00:00:00Z",
        source_version="usgs-fdsn-event-service",
        normalizer_version="1",
        source_url="https://earthquake.usgs.gov/fdsnws/event/1/query",
        request={"format": "geojson", "eventtype": "earthquake"},
        record_count=2,
        normalized_sha256="abc123",
        license="See USGS source policy",
        citation="USGS FDSN Event API",
        attribution="USGS Earthquake Hazards Program FDSN Event API",
        coverage={"status": "global-service", "notes": []},
        artifacts={"normalized": "normalized/earthquakes.csv"},
    )

    as_dict = manifest.to_dict()
    assert as_dict["schema_version"] == "knowledge-source/v1"
    assert SourceManifest.from_dict(as_dict) == manifest

    changed_retrieval = SourceManifest.from_dict({**as_dict, "retrieved_at": "2026-06-26T00:00:00Z"})
    assert changed_retrieval.stable_hash() == manifest.stable_hash()

    changed_request = SourceManifest.from_dict(
        {**as_dict, "request": {"format": "geojson", "eventtype": "earthquake", "minmagnitude": 4.5}}
    )
    assert changed_request.stable_hash() != manifest.stable_hash()


def test_source_manifest_rejects_unknown_schema_version():
    with pytest.raises(SourceManifestError):
        SourceManifest.from_dict({"schema_version": "bad"})


def test_source_registry_resolves_ordered_coverage_aware_source_sets():
    registry = default_source_registry()
    quebec = Bounds(min_lon=-77, min_lat=52, max_lon=-75, max_lat=53)
    california = Bounds(min_lon=-122.5, min_lat=37.0, max_lon=-121.5, max_lat=38.0)

    mineral_ids = [
        definition.id
        for definition in registry.resolve(family="mineral_occurrences", bounds=quebec)
    ]
    assert mineral_ids == ["ontario_mineral_deposit_inventory", "sigeom_mineral_occurrences"]
    assert registry.resolve(family="mineral_occurrences", bounds=california) == []

    selected = registry.resolve(
        family="earthquake_events",
        options={"sources": ["emsc_fdsn_events", "usgs_fdsn_events"]},
    )
    assert [definition.id for definition in selected] == ["usgs_fdsn_events", "emsc_fdsn_events"]

    with pytest.raises(SourceRegistryError):
        registry.resolve(family="active_faults", source_id="emsc_fdsn_events")


def test_find_latest_manifest_prefers_default_then_sorted_version(tmp_path):
    root = tmp_path / "sources"
    source_root = root / "usgs_fdsn_events"
    (source_root / "2024").mkdir(parents=True)
    (source_root / "2025").mkdir()
    (source_root / "2024" / "manifest.json").write_text("{}", encoding="utf-8")
    (source_root / "2025" / "manifest.json").write_text("{}", encoding="utf-8")

    assert find_latest_manifest(root, "usgs_fdsn_events") == source_root / "2025" / "manifest.json"

    (source_root / "default").mkdir()
    (source_root / "default" / "manifest.json").write_text("{}", encoding="utf-8")
    assert find_latest_manifest(root, "usgs_fdsn_events") == source_root / "default" / "manifest.json"
    assert find_latest_manifest(root, "usgs_fdsn_events", preferred_version="2024") == source_root / "2024" / "manifest.json"


def test_emsc_fdsn_adapter_builds_json_query_and_normalizes_geojson():
    adapter = FdsnEventSourceAdapter(
        source_id="emsc_fdsn_events",
        base_url=EMSC_EVENT_BASE_URL,
        default_profile=EMSC_DEFAULT_PROFILE,
        client=object(),
    )
    bounds = Bounds(min_lon=12, min_lat=41, max_lon=13, max_lat=42)

    params = adapter.query_params({"minmagnitude": "4.0"}, bounds=bounds)

    assert params["format"] == "json"
    assert params["eventtype"] == "earthquake"
    assert params["minlongitude"] == 12.0
    assert params["maxlongitude"] == 13.0
    assert params["minmagnitude"] == 4.0

    records = normalize_geojson_events(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "emsc2026abcd",
                    "properties": {
                        "time": "2026-01-01T00:00:00Z",
                        "mag": 5.1,
                        "magType": "mw",
                        "source_id": "EMSC",
                        "source_catalog": "EMSC-RTS",
                    },
                    "geometry": {"type": "Point", "coordinates": [12.5, 41.5, 10]},
                }
            ],
        }
    )

    assert records[0]["event_id"] == "emsc2026abcd"
    assert records[0]["longitude"] == 12.5


def test_wfs_adapters_build_queries_and_normalize_features():
    scenarios = (
        (
            "diss",
            DissSeismogenicSourceAdapter(client=object()),
            Bounds(min_lon=12, min_lat=41, max_lon=13, max_lat=42),
            "DISS331:iss331",
            "12.0,41.0,13.0,42.0,CRS:84",
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "iss-1",
                        "properties": {"name": "IT Source", "slip_type": "reverse"},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[12, 41], [13, 42]],
                        },
                    }
                ],
            },
        ),
        (
            "sigeom",
            SigeomMineralOccurrenceAdapter(client=object()),
            Bounds(min_lon=-77, min_lat=52, max_lon=-75, max_lat=53),
            "SGM:Substances_metalliques",
            "-77.0,52.0,-75.0,53.0,CRS:84",
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "NOM_CORPS_MINR": "Junior",
                            "SUBST_PRINC": "Zinc; Plomb",
                            "ETAT_CORPS_MINR": "Indice, aucun travail",
                        },
                        "geometry": {"type": "Point", "coordinates": [-76.0, 52.5]},
                    }
                ],
            },
        ),
    )

    for name, adapter, bounds, type_name, expected_bbox, payload in scenarios:
        params = adapter.query_params(bounds, type_name=type_name)

        assert params["service"] == "WFS"
        assert params["request"] == "GetFeature"
        assert params["typeNames"] == type_name
        assert params["outputFormat"] == "application/json"
        assert params["srsName"] == "CRS:84"
        assert params["bbox"] == expected_bbox

        if name == "diss":
            properties = adapter.normalize_geojson(payload)["features"][0]["properties"]
            assert properties["source_id"] == "diss_seismogenic_sources"
            assert properties["raw_properties"]["name"] == "IT Source"
        else:
            records = normalize_sigeom_features(payload)
            assert records[0]["name"] == "Junior"
            assert records[0]["primary_commodity"] == "Zinc; Plomb"
            assert records[0]["status"] == "Indice, aucun travail"
            assert records[0]["longitude"] == -76.0


def test_usgs_chunking_raises_when_subday_window_still_overflows():
    adapter = UsgsFdsnEventAdapter(client=object())

    with pytest.raises(SourceQueryError):
        adapter.split_time_window(
            {"starttime": "2026-01-01T00:00:00Z", "endtime": "2026-01-01T12:00:00Z"},
            lambda _profile: 20001,
        )


def test_usgs_fetch_requires_knowledge_network_extra(monkeypatch):
    adapter = UsgsFdsnEventAdapter(client=None)
    monkeypatch.setattr("stratigraphic_amenity.knowledge.sources.usgs_events._httpx_module", lambda: None)

    with pytest.raises(OptionalDependencyError):
        adapter.count({})


def test_gem_normalizer_preserves_raw_properties_and_parses_tuples(tmp_path):
    source = tmp_path / "faults.geojson"
    source.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "Tuple Fault", "average_dip": "(45,30,60)"},
                        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    adapter = GemActiveFaultSourceAdapter(client=object())

    normalized = adapter.normalize_geojson(json.loads(source.read_text(encoding="utf-8")))

    properties = normalized["features"][0]["properties"]
    assert properties["raw_properties"]["average_dip"] == "(45,30,60)"
    assert properties["average_dip_uncertainty"] == {"most_likely": 45, "min": 30, "max": 60}
