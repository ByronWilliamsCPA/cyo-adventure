"""optimize_cover downscales to a small WebP."""

import io

import pytest
from PIL import Image

from cyo_adventure.covers.optimize import optimize_cover

pytestmark = pytest.mark.unit


def _png(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (120, 90, 200)).save(buf, format="PNG")
    return buf.getvalue()


def test_output_is_webp_and_downscaled():
    out = optimize_cover(_png(1024, 1536), max_width=800)
    assert out[:4] == b"RIFF"
    assert out[8:12] == b"WEBP"
    with Image.open(io.BytesIO(out)) as img:
        assert img.width == 800
        assert img.height == 1200  # 2:3 preserved


def test_respects_byte_ceiling_via_quality_stepdown():
    # A noisy image is hard to compress; assert the ceiling is honored.
    import random

    rnd = random.Random(0)
    buf = io.BytesIO()
    noise = Image.new("RGB", (1200, 1800))
    noise.putdata(
        [
            (rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255))
            for _ in range(1200 * 1800)
        ]
    )
    noise.save(buf, format="PNG")
    out = optimize_cover(buf.getvalue(), max_width=800, quality=80, max_bytes=60_000)
    assert len(out) <= 60_000
