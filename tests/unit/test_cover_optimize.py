"""optimize_cover downscales to a small WebP and honors a soft byte ceiling.

The byte ceiling is a target, not a hard requirement: quality is stepped
down toward a floor, but the floor is a backstop that must never be crossed
into an invalid (negative) Pillow quality value, and the function must
never raise on a legitimately hard-to-compress source.
"""

import io
import math
import random

import pytest
from PIL import Image, UnidentifiedImageError

from cyo_adventure.covers.optimize import optimize_cover

pytestmark = pytest.mark.unit


def _png(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (120, 90, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _gradient_png(width: int, height: int) -> bytes:
    """A smooth gradient: highly compressible, quality-sensitive at small sizes."""
    img = Image.new("RGB", (width, height))
    pixels = [
        (
            int((math.sin(x / 7.0) + 1) * 127),
            int((math.sin(y / 11.0) + 1) * 127),
            int((math.sin((x + y) / 5.0) + 1) * 127),
        )
        for y in range(height)
        for x in range(width)
    ]
    img.putdata(pixels)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _noise_png(width: int, height: int, seed: int = 0) -> bytes:
    """Random noise: adversarially incompressible, used only where that's the point."""
    rnd = random.Random(seed)
    img = Image.new("RGB", (width, height))
    img.putdata(
        [
            (rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255))
            for _ in range(width * height)
        ]
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_output_is_webp_and_downscaled():
    out = optimize_cover(_png(1024, 1536), max_width=800)
    assert out[:4] == b"RIFF"
    assert out[8:12] == b"WEBP"
    with Image.open(io.BytesIO(out)) as img:
        assert img.width == 800
        assert img.height == 1200  # 2:3 preserved


def test_step_down_lands_under_ceiling_above_floor():
    """A compressible image that needs one step-down, landing under ceiling at q>=floor.

    q=80 on this source is ~17KB, q=70 is ~15KB; a 16KB ceiling forces exactly
    one step down and the result legitimately satisfies the ceiling.
    """
    source = _gradient_png(300, 450)
    out = optimize_cover(source, max_width=300, quality=80, max_bytes=16_000)
    assert out[:4] == b"RIFF"
    assert len(out) <= 16_000


def test_floor_reached_returns_without_raising_and_logs_warning(
    caplog: pytest.LogCaptureFixture,
):
    """A hard-to-compress source with a tiny ceiling still returns valid WebP.

    The floor is hit (never satisfies the ceiling); the function must not
    raise and must emit exactly one structured over-ceiling warning.
    """
    source = _noise_png(300, 450)
    with caplog.at_level("WARNING"):
        out = optimize_cover(source, max_width=300, quality=80, max_bytes=1_000)
    assert out[:4] == b"RIFF"
    assert out[8:12] == b"WEBP"
    assert "cover_over_size_ceiling" in caplog.text


def test_normal_under_ceiling_return_does_not_warn(caplog: pytest.LogCaptureFixture):
    """The common case (under ceiling on the first pass) logs nothing."""
    source = _png(400, 600)
    with caplog.at_level("WARNING"):
        out = optimize_cover(source, max_width=400, quality=80, max_bytes=256_000)
    assert out[:4] == b"RIFF"
    assert "cover_over_size_ceiling" not in caplog.text


def test_non_multiple_of_ten_quality_never_crashes():
    """Regression: a non-10-multiple quality with a hard source must not raise.

    Before the fix, _QUALITY_FLOOR=1 let the step-down loop pass a negative
    quality (85 -> 75 -> ... -> 5 -> -5) to Pillow's WEBP encoder, raising
    ValueError. This must return valid bytes instead.
    """
    source = _noise_png(300, 450)
    out = optimize_cover(source, max_width=300, quality=85, max_bytes=1_000)
    assert out[:4] == b"RIFF"
    assert out[8:12] == b"WEBP"


@pytest.mark.unit
def test_optimize_cover_undecodable_bytes_raises_unidentified_image_error() -> None:
    """Provider bytes that are not an image raise UnidentifiedImageError."""
    # Intentionally uncaught in optimize_cover: covers/service.py treats any
    # exception from this function as a failed cover (cover_status="failed").
    with pytest.raises(UnidentifiedImageError):
        optimize_cover(b"garbage-not-an-image")


@pytest.mark.unit
def test_optimize_cover_empty_bytes_raises_unidentified_image_error() -> None:
    """An empty provider payload raises UnidentifiedImageError, not a silent pass."""
    with pytest.raises(UnidentifiedImageError):
        optimize_cover(b"")


@pytest.mark.unit
def test_optimize_cover_truncated_png_raises_os_error() -> None:
    """A PNG cut off mid-stream fails at decode with OSError."""
    # The header parses (Image.open succeeds), but the forced full decode in
    # convert("RGB") hits the missing tail and raises.
    source = _png(400, 600)
    truncated = source[: len(source) // 2]
    with pytest.raises(OSError, match="truncated"):
        optimize_cover(truncated)


@pytest.mark.unit
def test_optimize_cover_zero_max_width_raises_value_error() -> None:
    """A misconfigured max_width of 0 propagates Pillow's ValueError."""
    # Documents that an invalid COVER_MAX_WIDTH is surfaced as a job failure
    # (via the service's failed-status handler) rather than producing a
    # degenerate zero-width image.
    source = _png(400, 600)
    with pytest.raises(ValueError, match="width must be > 0"):
        optimize_cover(source, max_width=0)
