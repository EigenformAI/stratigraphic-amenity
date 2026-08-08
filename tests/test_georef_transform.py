"""Affine fit + reprojection from ground control points to EPSG:4326 Bounds.

The deterministic core a VLM cannot do reliably: fit a pixel->world affine from
grid tick GCPs, then reproject the map extent corners from the projected CRS to
lon/lat and assemble a valid Bounds.
"""

import pyproj
import pytest

import stratigraphic_amenity.georef.transform as transform_module
from stratigraphic_amenity.georef import GeoReference, GroundControlPoint, fit_affine, georeference_bounds
from stratigraphic_amenity.georef.errors import AffineFitError
from stratigraphic_amenity.knowledge import Bounds


def _gcp(px, py, wx, wy):
    return GroundControlPoint(pixel_x=px, pixel_y=py, world_x=wx, world_y=wy)


# --- affine fitting ---------------------------------------------------------

def test_fit_affine_two_gcps_axis_aligned():
    # Pixel y grows downward while northing decreases -> negative y scale.
    gcps = [_gcp(0, 0, 600000, 5400000), _gcp(1000, 1000, 700000, 5300000)]
    affine = fit_affine(gcps)
    # world_x = 100*px + 600000 ; world_y = -100*py + 5400000
    wx, wy = affine.apply(500, 500)
    assert wx == pytest.approx(650000)
    assert wy == pytest.approx(5350000)
    assert affine.residual == pytest.approx(0.0, abs=1e-6)


def test_fit_affine_three_gcps_exact_fit():
    gcps = [
        _gcp(0, 0, 660000, 5400000),
        _gcp(1000, 0, 690000, 5400000),
        _gcp(0, 1000, 660000, 5360000),
    ]
    affine = fit_affine(gcps)
    wx, wy = affine.apply(1000, 1000)
    assert wx == pytest.approx(690000)
    assert wy == pytest.approx(5360000)
    # Exact fit up to float64 lstsq roundoff on ~5.4e6-magnitude coords (sub-mm).
    assert affine.residual == pytest.approx(0.0, abs=1e-3)


def test_fit_affine_one_gcp_raises():
    with pytest.raises(AffineFitError):
        fit_affine([_gcp(0, 0, 1, 1)])


def test_fit_affine_two_gcps_sharing_a_pixel_row_raises():
    # Same py -> cannot solve the northing axis.
    with pytest.raises(AffineFitError):
        fit_affine([_gcp(0, 0, 1, 1), _gcp(10, 0, 2, 1)])


def test_fit_affine_collinear_gcps_raises():
    gcps = [_gcp(0, 0, 0, 0), _gcp(1, 1, 1, 1), _gcp(2, 2, 2, 2)]
    with pytest.raises(AffineFitError):
        fit_affine(gcps)


# --- end-to-end georeferencing ---------------------------------------------

def test_georeference_bounds_utm15n_to_wgs84():
    gcps = [_gcp(0, 0, 660000, 5400000), _gcp(1000, 1000, 690000, 5360000)]
    ref = georeference_bounds(
        crs="UTM N83 Zone 15", gcps=gcps, pixel_extent=(0, 0, 1000, 1000)
    )
    assert isinstance(ref, GeoReference)
    assert ref.crs == "EPSG:26915"
    assert isinstance(ref.bounds, Bounds)

    # Independently reproject the four corners and compare.
    t = pyproj.Transformer.from_crs(26915, 4326, always_xy=True)
    corners = [(660000, 5400000), (690000, 5400000), (690000, 5360000), (660000, 5360000)]
    lons, lats = zip(*[t.transform(e, n) for e, n in corners])
    assert ref.bounds.min_lon == pytest.approx(min(lons), abs=1e-6)
    assert ref.bounds.max_lon == pytest.approx(max(lons), abs=1e-6)
    assert ref.bounds.min_lat == pytest.approx(min(lats), abs=1e-6)
    assert ref.bounds.max_lat == pytest.approx(max(lats), abs=1e-6)

    # Sanity: this is the Shebandowan belt area near Thunder Bay, Ontario.
    assert -92 < ref.bounds.min_lon and ref.bounds.max_lon < -89
    assert 47 < ref.bounds.min_lat and ref.bounds.max_lat < 50


def test_georeference_lonlat_to_pixel_roundtrips_pixel_to_lonlat():
    gcps = [_gcp(167, 99, 660000, 5400000), _gcp(1175, 1238, 690000, 5360000)]
    ref = georeference_bounds(crs=26915, gcps=gcps, pixel_extent=(23, 20, 1332, 1344))
    # Round-trip a pixel out through lon/lat and back; must return the same pixel.
    lon, lat = ref.pixel_to_lonlat(800.0, 600.0)
    px, py = ref.lonlat_to_pixel(lon, lat)
    assert px == pytest.approx(800.0, abs=1e-3)
    assert py == pytest.approx(600.0, abs=1e-3)


def test_georeference_reports_non_diagnostic_exact_fit_with_units():
    ref = georeference_bounds(
        crs=4284,
        gcps=[_gcp(0, 0, 66, 53), _gcp(1000, 1000, 71, 49)],
        pixel_extent=(0, 0, 1000, 1000),
    )

    assert ref.fit_method == "axis-aligned-exact-2gcp"
    assert ref.residual_units == "degree"
    assert ref.residual_m == pytest.approx(0.0, abs=1e-6)
    assert ref.residual_diagnostic is False
    assert ref.holdout_error is None
    assert any("residual_not_diagnostic" in warning for warning in ref.warnings)


def test_georeference_warns_on_nonstandard_axis_directions():
    ref = georeference_bounds(
        crs=4284,
        gcps=[_gcp(0, 0, 53, 66), _gcp(1000, 1000, 49, 71)],
        pixel_extent=(0, 0, 1000, 1000),
    )

    assert any("nonstandard_x_direction:a<=0" in warning for warning in ref.warnings)
    assert any("nonstandard_y_direction:e>=0" in warning for warning in ref.warnings)


def test_georeference_reports_holdout_and_pixel_errors_for_blunder():
    gcps = [
        _gcp(0, 0, 66.0, 53.0),
        _gcp(1000, 0, 71.0, 53.0),
        _gcp(0, 1000, 66.0, 49.0),
        _gcp(1000, 1000, 71.1, 49.0),
    ]
    ref = georeference_bounds(crs=4284, gcps=gcps, pixel_extent=(0, 0, 1000, 1000))

    assert ref.fit_method == "affine-least-squares"
    assert ref.residual_diagnostic is True
    assert ref.residual_m > 1000
    assert ref.holdout_error is not None and ref.holdout_error > 1000
    assert max(ref.gcp_pixel_errors) > 1


def test_projected_crs_residual_is_reported_in_metres():
    gcps = [
        _gcp(0, 0, 660000, 5400000),
        _gcp(1000, 0, 690000, 5400000),
        _gcp(0, 1000, 660000, 5360000),
        _gcp(1000, 1000, 690100, 5360000),
    ]
    ref = georeference_bounds(crs=26915, gcps=gcps, pixel_extent=(0, 0, 1000, 1000))

    assert ref.residual_units == "metre"
    assert ref.residual_m == pytest.approx(ref.residual, rel=0.02)


def test_three_gcp_exact_fit_is_not_diagnostic():
    ref = georeference_bounds(
        crs=4284,
        gcps=[
            _gcp(0, 0, 66, 53),
            _gcp(1000, 0, 71, 53),
            _gcp(0, 1000, 66, 49),
        ],
        pixel_extent=(0, 0, 1000, 1000),
    )

    assert ref.fit_method == "affine-exact-3gcp"
    assert ref.residual_diagnostic is False
    assert ref.holdout_error is None


def test_nonfinite_gcp_is_rejected():
    with pytest.raises(AffineFitError, match="finite"):
        fit_affine([_gcp(0, 0, 66, 53), _gcp(1000, 1000, float("inf"), 49)])


def test_nonfinite_metric_is_reported_as_unavailable(monkeypatch):
    monkeypatch.setattr(transform_module, "_error_metres", lambda *_args: float("inf"))

    ref = georeference_bounds(
        crs=4284,
        gcps=[_gcp(0, 0, 66, 53), _gcp(1000, 1000, 71, 49)],
        pixel_extent=(0, 0, 1000, 1000),
    )

    assert ref.residual_m is None
    assert any("metric_error_unavailable" in warning for warning in ref.warnings)
