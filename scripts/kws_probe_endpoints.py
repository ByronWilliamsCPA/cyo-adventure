"""Prove the two KWS return legs are reachable at a deployed origin.

Both KWS return URLs are registered by hand in Epic's Control Panel, and KWS
gives no way to test one from its side. So before registering anything, and
before drawing any conclusion from a webhook that never arrives, confirm from
outside that the URLs answer as OUR application.

Run recipe::

    uv run python scripts/kws_probe_endpoints.py \\
        --origin https://cyo-staging.williamshome.family

Why the assertions look paranoid
--------------------------------
This host has produced a false pass on exactly this shape of check before: a
path fronted by nginx answered ``200 OK`` from a hardcoded stub while the
application behind it never ran, and a documented "verified 200" carried that
anti-oracle for a month. A missing route can also fall through to the SPA and
answer ``200 text/html``, which looks healthy and proves nothing.

So no verdict here rests on a status code alone. Each probe asserts PROVENANCE:
a JSON error body is FastAPI's own error envelope, and the redirect page is
identified by a marker string it renders. The review question this encodes: if
a hardcoded stub at that path would satisfy the assertion, the assertion is
worthless.

What it sends, and why it is safe anywhere
------------------------------------------
The webhook probe posts an empty JSON object with NO signature header. The
receiver authenticates before it parses, so an unsigned delivery is rejected at
the signature stage and can never resolve a verification, in any environment.
The redirect probe is a bare GET with no query string, which fails the same way.
Neither probe can write anything, so this is safe to point at production.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import httpx

_RETURN_PATH = "/api/v1/consent/kws/return"
_WEBHOOK_PATH = "/api/v1/webhooks/kws/parent-verified"

# Rendered by api/kws_redirect.py's "could not confirm" page. Asserting on it
# is what separates our 400 from any other 400 an intermediary might invent.
_UNCONFIRMED_MARKER = "We could not confirm this link"

_JSON = "application/json"
_HTML = "text/html"


@dataclass(frozen=True, slots=True)
class Verdict:
    """One probe's outcome.

    Attributes:
        label: Which leg was probed.
        ready: Whether the route is live AND its secret is configured.
        detail: The operator-facing explanation, including what to do next.
    """

    label: str
    ready: bool
    detail: str


def _content_type(response: httpx.Response) -> str:
    """Return the response's media type without parameters.

    Args:
        response: The response to inspect.

    Returns:
        str: The lowercased media type, e.g. ``application/json``.
    """
    return response.headers.get("content-type", "").split(";")[0].strip().lower()


def _classify_return(response: httpx.Response) -> Verdict:
    """Judge the redirect return leg from an unsigned, parameterless GET.

    Args:
        response: The probe response.

    Returns:
        Verdict: The outcome and what it implies.
    """
    media = _content_type(response)
    label = "redirect return"

    if response.status_code == 400 and media == _HTML:
        if _UNCONFIRMED_MARKER in response.text:
            return Verdict(label, ready=True, detail="live, verification secret set")
        return Verdict(
            label,
            ready=False,
            detail=(
                "400 HTML but without our page marker: something other than "
                "this application is answering"
            ),
        )

    if response.status_code == 400 and media == _JSON:
        return Verdict(
            label,
            ready=False,
            detail=(
                "route is live but KWS_VERIFICATION_SECRET is unset. Expected "
                "until the Control Panel mints it; register the return URL first"
            ),
        )

    if response.status_code == 404 and media == _JSON:
        return Verdict(
            label,
            ready=False,
            detail="backend is reachable but this route is not deployed there",
        )

    return Verdict(label, ready=False, detail=_describe_foreign(response, media))


def _classify_webhook(response: httpx.Response) -> Verdict:
    """Judge the webhook leg from an unsigned POST.

    Args:
        response: The probe response.

    Returns:
        Verdict: The outcome and what it implies.
    """
    media = _content_type(response)
    label = "parent-verified webhook"

    if response.status_code == 401 and media == _JSON:
        return Verdict(label, ready=True, detail="live, webhook secret set")

    if response.status_code == 400 and media == _JSON:
        return Verdict(
            label,
            ready=False,
            detail="route is live but KWS_WEBHOOK_SECRET is unset",
        )

    if response.status_code == 404 and media == _JSON:
        return Verdict(
            label,
            ready=False,
            detail="backend is reachable but this route is not deployed there",
        )

    if response.status_code == 200:
        return Verdict(
            label,
            ready=False,
            detail=(
                "200 to an UNSIGNED delivery. Either an intermediary is "
                "answering instead of the application, or the receiver is "
                "accepting unauthenticated webhooks. Both are serious"
            ),
        )

    return Verdict(label, ready=False, detail=_describe_foreign(response, media))


def _describe_foreign(response: httpx.Response, media: str) -> str:
    """Describe a response that did not come from our handlers.

    Args:
        response: The probe response.
        media: Its media type.

    Returns:
        str: An operator-facing description naming the likely cause.
    """
    server = response.headers.get("server", "unknown")
    if response.is_redirect:
        return (
            f"{response.status_code} redirect to "
            f"{response.headers.get('location', '?')}: an ingress is rewriting "
            "the request before it reaches the application"
        )
    if response.status_code == 200 and media == _HTML:
        return (
            "200 HTML: this is the SPA or a stub, not the API. The route is "
            "not deployed at this origin"
        )
    return f"unrecognised: {response.status_code} {media} (server: {server})"


def _probe(client: httpx.Client, origin: str) -> list[Verdict]:
    """Run both probes against one origin.

    #CRITICAL: external resources: the webhook probe MUST stay unsigned. A
    signed probe would be a genuine delivery: the receiver would authenticate
    it, parse it, and attempt to resolve whatever attempt id it quoted. This
    script's safety to run anywhere, including production, rests entirely on
    never producing a valid signature.
    #VERIFY: tests/unit/test_kws_probe_endpoints.py::
    test_the_webhook_probe_sends_no_signature_header.

    Args:
        client: The HTTP client to use.
        origin: The scheme and host to probe, without a trailing slash.

    Returns:
        list[Verdict]: One verdict per leg, in probe order.
    """
    return [
        _classify_return(client.get(f"{origin}{_RETURN_PATH}")),
        _classify_webhook(client.post(f"{origin}{_WEBHOOK_PATH}", json={})),
    ]


def _run(args: argparse.Namespace) -> int:
    """Probe the origin and report.

    Args:
        args: The parsed command line.

    Returns:
        int: 0 when both legs are ready, 1 otherwise.
    """
    origin = args.origin.rstrip("/")
    print(f"probing {origin}")

    try:
        with httpx.Client(timeout=args.timeout, follow_redirects=False) as client:
            verdicts = _probe(client, origin)
    except httpx.HTTPError as exc:
        # A transport failure is the single most important outcome to report
        # clearly: it is indistinguishable, from KWS's side, from a webhook
        # they chose not to send.
        print(f"[UNREACHABLE] {type(exc).__name__}: {exc}")
        print(
            "[UNREACHABLE] KWS would see the same thing. Do not read a missing "
            "webhook as a vendor behaviour until this probe succeeds."
        )
        return 1

    for verdict in verdicts:
        status = "READY" if verdict.ready else "NOT READY"
        print(f"[{status}] {verdict.label}: {verdict.detail}")

    if all(verdict.ready for verdict in verdicts):
        print("[OK] both legs answer as this application. Safe to register.")
        return 0
    return 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line.

    Args:
        argv: Arguments to parse. Defaults to ``sys.argv[1:]``.

    Returns:
        argparse.Namespace: The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Check that both KWS return URLs answer as this application at a "
            "deployed origin. Read-only and safe against any environment."
        )
    )
    parser.add_argument(
        "--origin",
        required=True,
        help="Scheme and host, e.g. https://cyo-staging.williamshome.family",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Per-request timeout in seconds (default: 10).",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Entry point."""
    sys.exit(_run(_parse_args()))


if __name__ == "__main__":
    main()
