import importlib.util
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_contract():
    from stratigraphic_amenity import __version__

    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]

    assert metadata["name"] == "stratigraphic-amenity"
    assert metadata["version"] == "0.1.0"
    assert metadata["requires-python"] == ">=3.11,<3.12"
    assert metadata["scripts"] == {
        "stratigraphic-amenity-assets": "stratigraphic_amenity.asset_installer:main",
        "stratigraphic-amenity-mcp": "stratigraphic_amenity.mcp.server:main",
    }
    assert importlib.util.find_spec("stratigraphic_amenity") is not None
    assert importlib.util.find_spec("peace_tool_pool") is None
    assert __version__ == metadata["version"]
    detectors = metadata["optional-dependencies"]["detectors"]

    assert "opencv-python-headless==4.10.0.84" in detectors
    assert "py-cpuinfo==9.0.0" in detectors
    assert "opencv-python==4.10.0.84" not in detectors
