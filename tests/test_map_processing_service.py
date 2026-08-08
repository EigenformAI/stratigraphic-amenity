from pathlib import Path

import pytest

from stratigraphic_amenity.map_processing.config import MapProcessingConfig
from stratigraphic_amenity.map_processing.service import MapProcessingService
from stratigraphic_amenity.map_processing.types import Detection

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")


class FakeComponentDetector:
    def detect(self, image_path: str | Path):
        return {
            "main_map": [Detection(label="main_map", bbox=(0, 0, 60, 60), confidence=0.99)],
            "legend": [Detection(label="legend", bbox=(70, 10, 120, 40), confidence=0.95)],
            "title": [Detection(label="title", bbox=(0, 70, 40, 95), confidence=0.88)],
        }


class FakeLegendDetector:
    def detect(self, image_path: str | Path):
        return {
            "color_bndbox": [[2, 2, 10, 10]],
            "text_bndbox": [[15, 1, 42, 11]],
        }


def test_service_processes_image_and_writes_peace_metadata(tmp_path):
    image_path = tmp_path / "sample.png"
    image = np.full((100, 130, 3), 255, dtype=np.uint8)
    image[5:25, 5:25] = (0, 0, 255)  # Red patch inside main map for area estimate.
    image[12:20, 72:80] = (0, 0, 255)  # Red swatch inside legend crop.
    image[12:20, 88:105] = 0  # Synthetic legend text ink.
    assert cv2.imwrite(str(image_path), image)

    config = MapProcessingConfig(
        data_root=tmp_path / "data",
        model_root=tmp_path / "models",
        cache_root=tmp_path / "cache",
        dataset_source="usgs",
    )
    service = MapProcessingService(
        config=config,
        component_detector=FakeComponentDetector(),
        legend_detector=FakeLegendDetector(),
    )

    result = service.process_image(image_path, cache_identity="a" * 32)
    peace = result.to_peace_metadata()

    assert peace["name"] == "sample"
    assert peace["regions"]["main_map"] == [[0, 0, 60, 60]]
    assert peace["regions"]["legend"] == [[70, 10, 120, 40]]
    assert peace["legend"][0]["color"] == [255, 0, 0]
    assert peace["legend"][0]["color_hex"] == "#FF0000"
    assert peace["legend"][0]["area"] > 0
    assert result.legend[0].area_fraction > 0

    map_cache = config.cache_namespace_root / "maps" / ("a" * 32)
    metadata_path = map_cache / "metadata.json"
    crop_path = map_cache / "components" / "main_map_0.png"
    overlay_path = map_cache / "detections.png"
    assert metadata_path.exists()
    assert crop_path.exists()
    assert overlay_path.exists()

    overlay = cv2.imread(str(overlay_path))
    assert overlay is not None
    assert overlay.shape == image.shape
    assert not np.array_equal(overlay, image)
    inline_tag_pixels = overlay[2:14, 80:128].reshape(-1, 3)
    assert np.any(np.all(inline_tag_pixels == (0, 0, 255), axis=1))
    sampled_category_colors = {
        tuple(int(channel) for channel in overlay[1, 1]),
        tuple(int(channel) for channel in overlay[10, 70]),
        tuple(int(channel) for channel in overlay[70, 1]),
    }
    assert len(sampled_category_colors) == 3
    assert any(
        artifact.role == "detection_overlay" and Path(artifact.path) == overlay_path
        for artifact in result.artifacts
    )


def test_same_named_images_use_disjoint_cache_artifacts(tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first_image = first_dir / "image.png"
    second_image = second_dir / "image.png"
    assert cv2.imwrite(str(first_image), np.full((100, 130, 3), 255, dtype=np.uint8))
    assert cv2.imwrite(str(second_image), np.zeros((100, 130, 3), dtype=np.uint8))
    config = MapProcessingConfig(
        data_root=tmp_path / "data",
        model_root=tmp_path / "models",
        cache_root=tmp_path / "cache",
        dataset_source="usgs",
    )
    service = MapProcessingService(
        config=config,
        component_detector=FakeComponentDetector(),
        legend_detector=FakeLegendDetector(),
    )

    first = service.process_image(first_image, cache_identity="1" * 32)
    second = service.process_image(second_image, cache_identity="2" * 32)

    assert first.name == second.name == "image"
    assert {Path(item.path) for item in first.artifacts}.isdisjoint(
        {Path(item.path) for item in second.artifacts}
    )
