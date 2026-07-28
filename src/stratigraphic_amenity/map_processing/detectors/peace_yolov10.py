"""YOLOv10 detector adapter for PEACE's vendored Ultralytics fork."""

from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
from pathlib import Path
import sys
from typing import Any, Mapping

from ..errors import DetectorLoadError
from ..types import COMPONENT_LABELS, LEGEND_LABELS, Detection


COMPONENT_CLASS_NAMES = dict(enumerate(COMPONENT_LABELS))
LEGEND_CLASS_NAMES = {0: "color_bndbox", 1: "text_bndbox"}


def _load_yolov10_class(ultralytics_root: Path) -> Any:
    root = ultralytics_root.expanduser().resolve()
    init_path = root / "__init__.py"
    if not init_path.is_file():
        raise DetectorLoadError(
            "The managed PEACE YOLOv10 runtime is missing. Run "
            "`stratigraphic-amenity-assets peace-yolov10-runtime`."
        )
    if "os.sys.path.append" in init_path.read_text(encoding="utf-8"):
        raise DetectorLoadError(
            "The PEACE runtime still contains its source-tree path hook. Reinstall it with "
            "`stratigraphic-amenity-assets peace-yolov10-runtime --force`."
        )
    existing = sys.modules.get("ultralytics")
    if existing is not None:
        existing_file = Path(str(getattr(existing, "__file__", ""))).resolve()
        if existing_file != init_path:
            raise DetectorLoadError(
                "A different ultralytics package is already imported. Start a clean process so "
                "the attributed PEACE runtime can be loaded."
            )
        return getattr(existing, "YOLOv10")

    spec = importlib.util.spec_from_file_location(
        "ultralytics",
        init_path,
        submodule_search_locations=[str(root)],
    )
    if spec is None or spec.loader is None:
        raise DetectorLoadError(f"Unable to create an import spec for the PEACE runtime at {root}.")
    module = importlib.util.module_from_spec(spec)
    sys.modules["ultralytics"] = module
    try:
        with redirect_stdout(sys.stderr):
            spec.loader.exec_module(module)
        return getattr(module, "YOLOv10")
    except Exception as exc:  # noqa: BLE001 - backend imports fail for many optional reasons.
        sys.modules.pop("ultralytics", None)
        raise DetectorLoadError(
            "Unable to import the managed PEACE YOLOv10 runtime. Verify the 'detectors' extra "
            "and reinstall the runtime asset."
        ) from exc


def _to_list(value: Any) -> list[Any]:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "tolist"):
        return value.tolist()
    return list(value)


def _normalize_dict_result(
    result: Mapping[str, Any],
    class_names: Mapping[int, str],
) -> dict[str, list[Detection]]:
    detections = {label: [] for label in class_names.values()}
    for label, bboxes in result.items():
        label_name = str(label)
        detections.setdefault(label_name, [])
        for bbox in bboxes or []:
            detections[label_name].append(Detection(label=label_name, bbox=bbox))
    return detections


def _normalize_results_object(
    result: Any,
    class_names: Mapping[int, str],
) -> dict[str, list[Detection]]:
    detections = {label: [] for label in class_names.values()}
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return detections
    xyxy = _to_list(boxes.xyxy)
    confs = _to_list(boxes.conf)
    classes = _to_list(boxes.cls)
    for bbox, confidence, class_id in zip(xyxy, confs, classes):
        label = class_names.get(int(class_id), str(int(class_id)))
        detections.setdefault(label, [])
        detections[label].append(Detection(label=label, bbox=bbox, confidence=float(confidence)))
    return detections


def normalize_yolov10_result(
    result: Any,
    class_names: Mapping[int, str],
) -> dict[str, list[Detection]]:
    if isinstance(result, Mapping):
        return _normalize_dict_result(result, class_names)
    return _normalize_results_object(result, class_names)


class _YoloV10Detector:
    def __init__(
        self,
        model_path: str | Path,
        class_names: Mapping[int, str],
        ultralytics_root: str | Path,
    ):
        self.model_path = Path(model_path)
        self.class_names = dict(class_names)
        yolov10 = _load_yolov10_class(Path(ultralytics_root))
        with redirect_stdout(sys.stderr):
            self.model = yolov10(str(self.model_path))

    def detect(self, image_path: str | Path) -> dict[str, list[Detection]]:
        # save/save_txt/verbose/show must all be falsy or the PEACE fork replaces
        # each Results with a lossy name-keyed dict (no confidence) via write_results
        # (engine/predictor.py). save_txt defaults True, so it must be set explicitly.
        with redirect_stdout(sys.stderr):
            results = self.model.predict(
                source=str(image_path),
                verbose=False,
                save=False,
                save_txt=False,
                show=False,
            )
        if not results:
            return {label: [] for label in self.class_names.values()}
        return normalize_yolov10_result(results[0], self.class_names)


class YoloV10MapComponentDetector:
    def __init__(self, model_path: str | Path, ultralytics_root: str | Path):
        self._detector = _YoloV10Detector(model_path, COMPONENT_CLASS_NAMES, ultralytics_root)

    def detect(self, image_path: str | Path) -> dict[str, list[Detection]]:
        return self._detector.detect(image_path)


class YoloV10LegendDetector:
    def __init__(self, model_path: str | Path, ultralytics_root: str | Path):
        self._detector = _YoloV10Detector(model_path, LEGEND_CLASS_NAMES, ultralytics_root)

    def detect(self, image_path: str | Path) -> dict[str, list[list[int]]]:
        detections = self._detector.detect(image_path)
        return {
            label: [list(detection.bbox) for detection in detections.get(label, [])]
            for label in LEGEND_LABELS
        }
