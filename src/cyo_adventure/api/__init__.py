"""API package for CYO Adventure.

This package contains FastAPI routers and API-related functionality.
"""

from __future__ import annotations

from cyo_adventure.api.health import router as health_router

__all__ = ["health_router"]
