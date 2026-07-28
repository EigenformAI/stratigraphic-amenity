"""Environment parsing for the detector-preparation exposure gate."""

import pytest

from stratigraphic_amenity.mcp.adapter import detector_preparation_enabled


VARIABLE = "GEOMAP_MCP_ENABLE_DETECTOR_PREPARATION"


def test_preparation_is_enabled_when_unset(monkeypatch):
    monkeypatch.delenv(VARIABLE, raising=False)

    assert detector_preparation_enabled() is True


@pytest.mark.parametrize("value", ["", "   "])
def test_preparation_is_enabled_when_blank(monkeypatch, value):
    monkeypatch.setenv(VARIABLE, value)

    assert detector_preparation_enabled() is True


@pytest.mark.parametrize("value", ["true", "TRUE", " yes ", "1", "on", "y"])
def test_preparation_is_enabled_for_truthy_values(monkeypatch, value):
    monkeypatch.setenv(VARIABLE, value)

    assert detector_preparation_enabled() is True


@pytest.mark.parametrize("value", ["false", "FALSE", "0", "no", "off", "n"])
def test_preparation_is_disabled_for_falsey_values(monkeypatch, value):
    monkeypatch.setenv(VARIABLE, value)

    assert detector_preparation_enabled() is False


@pytest.mark.parametrize("value", ["flase", "disabled", "maybe"])
def test_unrecognized_values_fail_closed(monkeypatch, value):
    """A typo in the locking direction must not silently re-expose the tool."""

    monkeypatch.setenv(VARIABLE, value)

    assert detector_preparation_enabled() is False
