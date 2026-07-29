"""CRS string resolution for georeferencing.

A geologic map states its CRS as free text (e.g. "UTM N83 Zone 15"). The agent
should not have to know EPSG arithmetic, so resolve_crs turns common UTM/EPSG
strings into a canonical "EPSG:<code>".
"""

import pytest

from stratigraphic_amenity.georef import resolve_crs
from stratigraphic_amenity.georef.errors import CRSResolutionError


def test_resolve_valid_crs():
    rows = (
        (26915, "EPSG:26915"),
        ("epsg:26915", "EPSG:26915"),
        ("EPSG: 4326", "EPSG:4326"),
        ("UTM N83 Zone 15", "EPSG:26915"),
        ("WGS84 UTM Zone 15N", "EPSG:32615"),
        ("WGS 84 / UTM zone 15S", "EPSG:32715"),
        ("NAD27 UTM Zone 15", "EPSG:26715"),
        ("UTM Zone 15N", "EPSG:32615"),
    )

    for value, expected in rows:
        assert resolve_crs(value) == expected


def test_rejects_invalid_crs():
    for value in ("banana republic", "UTM NAD83 Zone 61"):
        with pytest.raises(CRSResolutionError):
            resolve_crs(value)
