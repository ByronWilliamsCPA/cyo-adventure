"""Guards that bound what the KWS integration is allowed to do (ADR-018).

One guard today, shared by both legs. It lives here rather than in either leg
so that the change which lifts it has a single place to edit and cannot lift it
for one leg while forgetting the other; a send leg that could run in production
while the receiver could not would email real parents into a void.
"""

from __future__ import annotations

from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import ConfigurationError


def require_non_production_kws_environment(*, action: str) -> None:
    """Refuse production KWS traffic while no verification record is persisted.

    #CRITICAL: data integrity: neither leg is safe against the production
    environment until a verification record exists. On the receive side a real
    delivery would be acknowledged and discarded, and KWS will not replay it on
    request. On the send side we would email a real parent, ask them to enter
    card details, and then have nowhere to record the outcome, which is worse:
    it spends a stranger's time and money on an experiment.

    Enforcing this in code rather than in a comment is what keeps "persistence
    before production" from being a promise nobody re-reads.
    #VERIFY: tests/unit/test_kws_webhook.py::
    test_production_environment_refuses_to_process and
    tests/unit/test_kws_client.py::test_production_environment_refuses_to_send.

    Args:
        action: What was being attempted, for the error message. Phrased as a
            verb clause, e.g. ``"accept a parent-verified delivery"``.

    Raises:
        ConfigurationError: When ``kws_environment`` is ``"production"``.
    """
    if settings.kws_environment != "production":
        return
    msg = (
        f"Refusing to {action}: this integration records no verification yet, "
        "so it must not run against the production KWS environment. Remove "
        "this guard in the change that adds the verification record."
    )
    raise ConfigurationError(msg)
