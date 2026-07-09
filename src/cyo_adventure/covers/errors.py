"""Cover generation errors."""


class CoverGenerationError(RuntimeError):
    """Raised when nano banana returns no usable image (incl. safety refusals)."""
