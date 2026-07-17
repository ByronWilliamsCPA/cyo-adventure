"""CYO Adventure.

A choose-your-own-adventure reading app for kids
"""

from importlib.metadata import PackageNotFoundError, version

# The single source of truth for the running version is the installed
# distribution metadata, which tracks pyproject.toml (bumped by the release
# workflow). A hardcoded literal here rotted at "0.1.0" while releases moved
# on, so /health and the OpenAPI info block misreported the version.
try:
    __version__ = version("cyo-adventure")
except PackageNotFoundError:  # pragma: no cover - source tree without install
    __version__ = "0.0.0"

__author__ = "Byron Williams"
__email__ = "byronawilliams@gmail.com"

__all__ = [
    "__author__",
    "__email__",
    "__version__",
]
