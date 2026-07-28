"""Inline previews are a different coordinate frame from the structured boxes.

Round-2 run A read region boxes off the 1010x1228 preview and reported them as the
detector's output, which is in the 1600x1946 source frame.
"""

import base64

import pytest

from stratigraphic_amenity.mcp.images import make_inline_preview


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGA"
    "WjR9awAAAABJRU5ErkJggg=="
)


def test_preview_metadata_declares_its_own_frame(tmp_path):
    pytest.importorskip("PIL")
    image = tmp_path / "map.png"
    image.write_bytes(PNG_1X1)

    preview = make_inline_preview(image, artifact_uri="geomap://artifacts/x")

    assert preview is not None
    assert preview["metadata"]["coordinate_frame"] == "preview"
