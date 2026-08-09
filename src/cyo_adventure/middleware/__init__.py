"""Security middleware for API applications.

This package provides production-ready security middleware implementing
OWASP best practices for web applications.
"""

from __future__ import annotations

from cyo_adventure.middleware.correlation import (
    CORRELATION_ID_HEADER,
    REQUEST_ID_HEADER,
    SPAN_ID_HEADER,
    TRACE_ID_HEADER,
    CorrelationMiddleware,
    correlation_context_processor,
    generate_correlation_id,
    get_correlation_id,
    get_request_id,
    get_span_id,
    get_trace_id,
    set_correlation_id,
)
from cyo_adventure.middleware.security import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    SSRFPreventionMiddleware,
    add_security_middleware,
)
from cyo_adventure.middleware.unit_of_work import (
    UNIT_OF_WORK_STATE_KEY,
    RequestUnitOfWork,
    UnitOfWorkMiddleware,
)

__all__ = [
    "CORRELATION_ID_HEADER",
    "REQUEST_ID_HEADER",
    "SPAN_ID_HEADER",
    "TRACE_ID_HEADER",
    "UNIT_OF_WORK_STATE_KEY",
    "BodySizeLimitMiddleware",
    "CorrelationMiddleware",
    "RateLimitMiddleware",
    "RequestUnitOfWork",
    "SSRFPreventionMiddleware",
    "SecurityHeadersMiddleware",
    "UnitOfWorkMiddleware",
    "add_security_middleware",
    "correlation_context_processor",
    "generate_correlation_id",
    "get_correlation_id",
    "get_request_id",
    "get_span_id",
    "get_trace_id",
    "set_correlation_id",
]
