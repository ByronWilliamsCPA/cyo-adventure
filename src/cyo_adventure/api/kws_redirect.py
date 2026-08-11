"""Browser return page for the KWS verification redirect leg (ADR-018).

``GET /api/v1/consent/kws/return`` is where a parent's BROWSER lands after
finishing at Epic's Parent Verification Service. KWS appends ``status``,
``externalPayload`` and ``signature`` to the return URL registered in the
Control Panel, and this route turns those three values into one of two
sentences on a page.

This route is DISPLAY-ONLY and must never touch verification state
------------------------------------------------------------------
#CRITICAL: security: ``verify_redirect_signature`` covers
``f"{status}:{external_payload}"`` with no timestamp and no nonce, so the
signed material is immutable and a valid return URL is a permanently
replayable bearer token: whoever sees it once, including the child, can
revisit it forever and it still verifies. It is therefore fit for choosing
which screen to render and for nothing else. ``api/kws_webhook.py``, whose
signed string carries a timestamp and which arrives server-to-server, is the
only leg allowed to create or advance a ``kws_verification`` row. A future
edit that reads or writes that table here reintroduces exactly the replay the
webhook exists to avoid.

The one write this route DOES make is the security audit row in ``_reject``,
which is the opposite kind of record: it attributes a REFUSED return to a
client address and cannot be provoked into asserting that anybody was
verified. Replaying a forged URL a thousand times writes a thousand rows
saying the same forgery was refused, which is the behaviour the audit trail is
for. The distinction to preserve is "no consent state", not "no bytes".
#VERIFY: tests/unit/test_kws_redirect.py::TestNoPersistence::
test_route_module_never_touches_verification_state.

Deliberately excluded from the OpenAPI schema
---------------------------------------------
``include_in_schema=False``. The frontend's axios client is generated from the
schema and committed with a CI drift check, so putting a browser-only landing
page in the schema would churn ``frontend/src/client/`` for a route no SPA
will ever call. The page is intentionally plain and self-contained: no
external assets, no scripts, and no reflected content, so there is nothing to
escape and nothing to fetch.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.consent import verify_redirect_signature
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import AuthenticationError, ConfigurationError
from cyo_adventure.security_audit import record_security_event
from cyo_adventure.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["kws"])

# The three query parameters KWS appends to the return URL. `externalPayload`
# keeps its camelCase spelling because it is read straight off the query
# string, not through a FastAPI parameter with an alias.
_STATUS_PARAM = "status"
_EXTERNAL_PAYLOAD_PARAM = "externalPayload"
_SIGNATURE_PARAM = "signature"

# Non-JSON spellings of "this parent is verified". Epic's documentation does
# not pin the `status` value's shape, and the JSON reading below is the
# better-evidenced one; these cover a bare token if the service sends one.
_AFFIRMATIVE_STATUS_TOKENS = frozenset({"true", "verified", "success"})

# The `code` on every audit row this route writes. A literal rather than the
# exception's own `error_code`, which is the generic class default at all 89
# other raise sites: a detection rule keyed on a forged verification return
# wants to find it without also matching every failed guardian login.
_REJECTION_CODE = "KWS_REDIRECT_UNVERIFIED"

# The URL is a bearer token with no expiry (see the module docstring), so at
# minimum do not invite a shared browser or an intermediary to keep a copy of
# the page it produced.
_NO_STORE = {"Cache-Control": "no-store"}


class _RedirectStatus(BaseModel):
    """The ``status`` query parameter read as a JSON object.

    Only ``verified`` is consumed. Anything else KWS puts in the blob is
    ignored rather than modelled, because this page has no use for it and a
    field added upstream must not turn a real return into a parse failure.
    """

    model_config = ConfigDict(extra="ignore")

    verified: bool = False


# Where the parent goes next. Every page below is otherwise a dead end: the
# parent arrives here from Epic's hosted flow, frequently by tapping a link in
# a mail app, so there is no history to go back through and, on a fresh
# browser, no session either. `/guardian` handles both: with a session it is
# the console, without one the SPA sends them to the guardian login.
#
# A ROOT-RELATIVE href, so the link is correct on whatever origin served the
# page and the page keeps referencing nothing external
# (tests/unit/test_kws_redirect.py::TestNoPersistence::
# test_success_page_is_self_contained pins that).
#
# #ASSUME: external-resources: mirrors GUARDIAN_CONSOLE_PATH in
# frontend/src/routes.ts. Nothing links the two, so moving the console route
# there lands a parent on the app's 404 page here.
# #VERIFY: tests/unit/test_kws_redirect.py::TestLanding::
# test_the_landing_path_matches_the_app_route, which reads the constant the SPA
# router actually uses. The sibling test_every_page_offers_a_way_back_into_the_app
# only proves a link is present, so it cannot catch a rename on the other side.
_APP_PATH = "/guardian"
_APP_LINK_LABEL = "Return to CYO Adventure"


def _render(*, title: str, heading: str, body: str) -> str:
    """Build a complete, self-contained HTML page.

    Every substitution comes from a module-level literal below, never from the
    query string, so this deliberately does no escaping: there is no
    caller-controlled text on the page to escape.

    The link back into the app is rendered on every page rather than only on
    the success page, because a parent whose verification did not complete is
    exactly the one who most needs a route back to try again.

    Note what that does not buy. Success and failure are already fully
    distinguishable by their headings, by design, so no non-disclosure property
    rests on the link being present in both. What ``TestDisclosure`` denies is
    discrimination among the four REJECTION causes, and those four already
    collapse onto one page; the link is symmetric because a dead end is bad on
    every outcome, not because an oracle depends on it.

    Args:
        title: The document title.
        heading: The single headline shown to the parent.
        body: One sentence of explanation under the headline.

    Returns:
        str: The rendered page.
    """
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="robots" content="noindex">\n'
        f"<title>{title}</title>\n"
        "<style>\n"
        "body { font-family: system-ui, sans-serif; margin: 0; padding: 2rem;\n"
        "       color: #1b1b1f; background: #f8f3e8; }\n"
        "main { max-width: 32rem; margin: 3rem auto; }\n"
        "h1 { font-size: 1.5rem; margin: 0 0 0.75rem; }\n"
        "p { font-size: 1rem; line-height: 1.5; margin: 0; }\n"
        # The app's own parchment surface and amber accent, copied as literals
        # rather than imported: this page must render with no stylesheet, no
        # font, and no script fetched from anywhere.
        #
        # Ink on the amber fill, not white. frontend/design-system/src/tokens.css
        # records amber-deep against white at 3.42:1, under the 4.5:1 WCAG AA
        # floor for normal text (1rem at weight 600 is not "large text"), and
        # prescribes ink on the fill instead; guardian.css's
        # `.intake-request__assign` is the in-app precedent. Do not restore a
        # light foreground here.
        "a { display: inline-block; margin-top: 1.75rem; padding: 0.7rem 1.2rem;\n"
        "    border-radius: 0.5rem; background: #c17b2a; color: #1b1b1f;\n"
        "    font-size: 1rem; font-weight: 600; text-decoration: none; }\n"
        "a:focus-visible { outline: 3px solid #1b1b1f; outline-offset: 3px; }\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        "<main>\n"
        f"<h1>{heading}</h1>\n"
        f"<p>{body}</p>\n"
        # #CRITICAL: security: rel="noreferrer" because the URL of THIS page is
        # itself a replayable signed credential (see the module docstring). The
        # global Referrer-Policy is strict-origin-when-cross-origin, which drops
        # the path and query only on CROSS-origin navigations; `/guardian` is
        # same-origin, so without this the full return URL, signature and all,
        # is sent as `Referer` and lands in whatever access log serves the app.
        # #VERIFY: tests/unit/test_kws_redirect.py::TestLanding::
        # test_the_way_back_sends_no_referrer.
        f'<a href="{_APP_PATH}" rel="noreferrer">{_APP_LINK_LABEL}</a>\n'
        "</main>\n"
        "</body>\n"
        "</html>\n"
    )


_VERIFIED_PAGE = _render(
    title="Verification complete",
    heading="Verification complete",
    body=(
        "Thank you. There is nothing else for you to do here. Head back to "
        "CYO Adventure to carry on, or close this window if you started on "
        "another device."
    ),
)

_NOT_VERIFIED_PAGE = _render(
    title="Verification not completed",
    heading="Verification was not completed",
    body=(
        "This verification did not finish, and nothing has changed on your "
        "account. You can start again from CYO Adventure whenever you are "
        "ready."
    ),
)

# One page for every rejection cause, so a caller cannot tell a tampered
# status from a wrong key from a missing signature. See `_reject`.
_UNCONFIRMED_PAGE = _render(
    title="Link could not be confirmed",
    heading="We could not confirm this link",
    body=(
        "This link is not one we can recognise. Please start the verification "
        "again from CYO Adventure."
    ),
)


async def _reject(request: Request, reason: str) -> HTMLResponse:
    """Record a refused return, then hand back the page the parent sees.

    The disclosure split is the same one ``api/kws_webhook.py::_reject`` makes,
    for the same reason: ``consent/kws_signature.py`` puts a precise
    discriminator in the exception's ``details``, and this app's error handler
    serialises ``details`` into the response body. Publishing it here would
    turn the page into an oracle, so the reason is logged and the caller gets
    one page that is byte-identical for every cause.

    Refusals are recorded here rather than by raising ``AuthenticationError``,
    which is how the other 89 raise sites reach ``record_security_event``. That
    route is unavailable to this one: the app's handler renders an
    ``AuthenticationError`` as a JSON 401, and this is a page a parent reads,
    not an API a client parses. Calling the recorder directly keeps both
    properties, and is safe to call from a handler because it owns a
    short-lived session of its own and never raises (``security_audit.py``).

    #CRITICAL: security: information disclosure (CWE-209). Every refusal out of
    this route must go through this function; returning the verifier's own
    exception would publish which check failed.
    #VERIFY: tests/unit/test_kws_redirect.py::TestDisclosure::
    test_every_rejection_cause_is_indistinguishable.

    #CRITICAL: security: OPS-005 -- this endpoint is unauthenticated, public,
    and renders "Verification complete", which makes it the most probe-worthy
    surface in the KWS integration. Bypassing the exception handler must not
    also bypass the durable audit trail the handler exists to feed, or forged
    returns become the one class of auth failure with no record.
    #VERIFY: tests/unit/test_kws_redirect.py::TestDisclosure::
    test_a_refused_return_is_recorded_as_a_security_event.

    Args:
        request: The inbound request, read for the client address, path, and
            method that the verifier itself has no access to.
        reason: The log-safe discriminator, never sent to the caller. Always
            one of ``kws_signature.py``'s fixed literals, never caller input,
            which is the contract ``record_security_event`` documents.

    Returns:
        HTMLResponse: The generic failure page, with a 400 so a forged link is
            not recorded as a successful page view.
    """
    client_ip = request.client.host if request.client is not None else None
    logger.warning(
        "kws_redirect_rejected",
        reason=reason,
        kws_environment=settings.kws_environment,
    )
    await record_security_event(
        event_type="security_auth_failed",
        reason=reason,
        code=_REJECTION_CODE,
        client_ip=client_ip,
        path=request.url.path,
        method=request.method,
        status_code=400,
    )
    return HTMLResponse(
        content=_UNCONFIRMED_PAGE, status_code=400, headers=dict(_NO_STORE)
    )


def _require_verification_configured() -> str:
    """Return the redirect leg's secret, refusing to run without one.

    Note this is ``kws_verification_secret``, NOT the webhook's
    ``kws_webhook_secret``: the two legs use different keys and different
    signed constructions. An unset key is not permission to believe an
    unsigned return, because every value on the URL is then attacker-chosen
    and the page would report "verified" to anyone who typed it.

    Returns:
        str: The configured verification secret.

    Raises:
        ConfigurationError: When no verification secret is configured. Renders
            as a 400 rather than a page, because this is an operator fault the
            parent cannot act on.
    """
    secret = settings.kws_verification_secret
    if secret is None or not secret.get_secret_value():
        msg = (
            "KWS_VERIFICATION_SECRET is not configured; refusing to render a "
            "verification result from an unverifiable redirect."
        )
        raise ConfigurationError(msg)
    return secret.get_secret_value()


def _reports_verified(status: str) -> bool:
    """Whether the signed ``status`` value says the parent was verified.

    Epic's PV Service API pages (Developer Portal, read 2026-08-10) give the
    return URL verbatim, and ``status`` is a URL-encoded JSON object:
    ``{"verified":true,"transactionId":"<id>","errorCode":null}``. That
    settles what an earlier ``#ASSUME`` here had to hedge. The documented
    shape is the JSON-object branch, and it matches the shape the
    ``parent-verified`` webhook uses for the same fact.

    #EDGE: external resources: the bare-token fallback (a plain
    ``verified``/``true``/``success`` string) is kept for a ``status`` that is
    not a JSON object. No documented response takes that shape, so it guards
    against an undocumented variant rather than a branch we expect to run.
    Anything neither branch recognises reads as NOT verified, which is the
    safe direction: this page writes nothing, and the webhook remains the
    authoritative record either way.
    #VERIFY: tests/unit/test_kws_redirect.py::TestStatusReading pins the JSON
    object, the JSON literal, the bare token, and the unrecognised cases.

    Args:
        status: The ``status`` query parameter, already signature-verified.

    Returns:
        bool: True when the value affirmatively reports a verified parent.
    """
    try:
        return _RedirectStatus.model_validate_json(status).verified
    except PydanticValidationError:
        # Not a JSON object. A JSON string arrives with its quotes intact, so
        # they are stripped before the token comparison.
        return status.strip().strip('"').strip().lower() in _AFFIRMATIVE_STATUS_TOKENS


@router.get(
    "/consent/kws/return",
    include_in_schema=False,
    response_class=HTMLResponse,
)
async def kws_verification_return(request: Request) -> HTMLResponse:
    """Render the parent-facing result of a KWS verification redirect.

    #CRITICAL: security: this handler reads only, by design. A signed return
    URL is replayable forever (module docstring), so the outcome it reports is
    a screen and never a record; ``api/kws_webhook.py`` is the write path. The
    audit row ``_reject`` writes is not an exception to that: see its docstring.
    #VERIFY: tests/unit/test_kws_redirect.py::TestNoPersistence::
    test_route_module_never_touches_verification_state.

    #ASSUME: data integrity: the signature covers the DECODED literal values,
    so the parameters are read off ``request.query_params``, which is
    Starlette's percent-decoded view. ``request.url.query`` is the encoded
    form and would never verify. A FastAPI-declared ``str`` parameter yields
    the identical decoded value, so the choice here is about shape rather than
    correctness: reading the mapping means a missing ``signature`` becomes a
    rejection page instead of a 422 about a missing field. The one residual
    hazard is inherent to form decoding rather than to either API: an
    UNENCODED ``+`` in the query string decodes to a space, so a sender that
    fails to percent-encode a literal ``+`` produces a value that will not
    verify.
    #VERIFY: tests/unit/test_kws_redirect.py::TestSignature::
    test_url_encoded_values_still_verify.

    Args:
        request: The inbound request, read for its query parameters only.

    Returns:
        HTMLResponse: The verified page, the not-verified page, or, for any
            return we cannot authenticate, the generic failure page.

    Raises:
        ConfigurationError: When no verification secret is configured.
    """
    secret = _require_verification_configured()

    # Unlike the webhook's body, a query string is already bounded by the
    # server's request-line limit, so there is no separate size cap here: the
    # HMAC input cannot exceed what uvicorn already refused to read.
    params = request.query_params
    status = params.get(_STATUS_PARAM, "")
    external_payload = params.get(_EXTERNAL_PAYLOAD_PARAM, "")
    signature = params.get(_SIGNATURE_PARAM, "")

    try:
        verify_redirect_signature(
            signature=signature,
            status=status,
            external_payload=external_payload,
            secret=secret,
        )
    except AuthenticationError as exc:
        reason = (exc.details or {}).get("reason") or "unspecified"
        return await _reject(request, str(reason))

    verified = _reports_verified(status)
    # No status blob and no correlation token in the log line: the first is
    # KWS's wording rather than a fact we need twice, and the second is our
    # own per-attempt token, whose presence is worth knowing and whose value
    # is not.
    logger.info(
        "kws_redirect_return",
        verified=verified,
        has_external_payload=bool(external_payload),
        kws_environment=settings.kws_environment,
        kws_environment_label=settings.kws_environment_label,
    )
    page = _VERIFIED_PAGE if verified else _NOT_VERIFIED_PAGE
    return HTMLResponse(content=page, status_code=200, headers=dict(_NO_STORE))
