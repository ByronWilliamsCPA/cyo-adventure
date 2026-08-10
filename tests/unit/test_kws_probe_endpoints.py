"""Tests for ``scripts/kws_probe_endpoints.py``.

``scripts/`` is not an importable package (no ``__init__.py``, by design), so
the module under test is loaded from its file path via importlib, mirroring
``tests/unit/test_backup_database.py``.

The classification table is the whole product here. A probe that reports READY
for a response our application did not produce is worse than no probe at all,
because it converts an unverified assumption into a recorded verification, so
every false-pass shape gets its own test.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    import pytest

_SPEC = importlib.util.spec_from_file_location(
    "kws_probe_endpoints",
    Path(__file__).resolve().parents[2] / "scripts" / "kws_probe_endpoints.py",
)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - import plumbing
    msg = "could not load scripts/kws_probe_endpoints.py"
    raise RuntimeError(msg)
script = importlib.util.module_from_spec(_SPEC)
sys.modules["kws_probe_endpoints"] = script
_SPEC.loader.exec_module(script)


_ORIGIN = "https://cyo-staging.example.test"


def _html(status: int, body: str) -> httpx.Response:
    """Build an HTML response.

    Args:
        status: The status code.
        body: The body text.

    Returns:
        httpx.Response: The response.
    """
    return httpx.Response(status, headers={"content-type": "text/html"}, text=body)


def _json(status: int) -> httpx.Response:
    """Build a JSON error-envelope response.

    Args:
        status: The status code.

    Returns:
        httpx.Response: The response.
    """
    return httpx.Response(status, json={"error": "x"})


class TestClassifyReturn:
    """The redirect return leg's classification table."""

    def test_our_page_is_ready(self) -> None:
        body = f"<h1>{script._UNCONFIRMED_MARKER}</h1>"
        assert script._classify_return(_html(400, body)).ready

    def test_a_400_html_without_our_marker_is_not_ready(self) -> None:
        # Status and content type both match; only the marker separates our
        # page from an intermediary's error page.
        assert not script._classify_return(_html(400, "<h1>Bad Request</h1>")).ready

    def test_a_json_400_reports_the_missing_verification_secret(self) -> None:
        verdict = script._classify_return(_json(400))
        assert not verdict.ready
        assert "KWS_VERIFICATION_SECRET" in verdict.detail

    def test_a_json_404_reports_the_route_as_undeployed(self) -> None:
        verdict = script._classify_return(_json(404))
        assert not verdict.ready
        assert "not deployed" in verdict.detail

    def test_a_200_html_spa_fallback_is_not_ready(self) -> None:
        # The headline anti-oracle: this is what a missing route looks like
        # behind an SPA fallback, and it reads as healthy to a status-only check.
        verdict = script._classify_return(_html(200, "<html>app shell</html>"))
        assert not verdict.ready
        assert "not deployed" in verdict.detail


class TestClassifyWebhook:
    """The webhook leg's classification table."""

    def test_a_json_401_is_ready(self) -> None:
        assert script._classify_webhook(_json(401)).ready

    def test_a_json_400_reports_the_missing_webhook_secret(self) -> None:
        verdict = script._classify_webhook(_json(400))
        assert not verdict.ready
        assert "KWS_WEBHOOK_SECRET" in verdict.detail

    def test_a_json_404_reports_the_route_as_undeployed(self) -> None:
        verdict = script._classify_webhook(_json(404))
        assert not verdict.ready
        assert "not deployed" in verdict.detail

    def test_a_200_to_an_unsigned_post_is_never_ready(self) -> None:
        # Either an intermediary answered, or we accept unauthenticated
        # webhooks. There is no reading of this that is good.
        verdict = script._classify_webhook(httpx.Response(200, json={"ok": True}))
        assert not verdict.ready
        assert "UNSIGNED" in verdict.detail

    def test_a_redirect_names_the_ingress(self) -> None:
        response = httpx.Response(307, headers={"location": "https://elsewhere"})
        verdict = script._classify_webhook(response)
        assert not verdict.ready
        assert "ingress" in verdict.detail


class TestProbe:
    """What actually goes on the wire."""

    def test_the_webhook_probe_sends_no_signature_header(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _json(401)

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            script._probe(client, _ORIGIN)

        posts = [request for request in seen if request.method == "POST"]
        assert len(posts) == 1
        # The safety property that makes this script safe against production:
        # no signature means the receiver rejects before it parses, so the
        # probe can never resolve a verification.
        assert "x-kws-signature" not in posts[0].headers

    def test_both_paths_are_probed(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.path)
            return _json(401)

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            script._probe(client, _ORIGIN)

        assert seen == [script._RETURN_PATH, script._WEBHOOK_PATH]


class TestRun:
    """Exit codes, which is what a caller gates on."""

    def _args(self) -> argparse.Namespace:
        """Build a parsed command line.

        Returns:
            argparse.Namespace: Arguments for the probed origin.
        """
        return argparse.Namespace(origin=_ORIGIN, timeout=1.0)

    def test_a_fully_ready_origin_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ready = [
            script.Verdict("redirect return", ready=True, detail="live"),
            script.Verdict("webhook", ready=True, detail="live"),
        ]
        monkeypatch.setattr(script, "_probe", lambda *_: ready)

        assert script._run(self._args()) == 0

    def test_one_unready_leg_exits_non_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mixed = [
            script.Verdict("redirect return", ready=True, detail="live"),
            script.Verdict("webhook", ready=False, detail="secret unset"),
        ]
        monkeypatch.setattr(script, "_probe", lambda *_: mixed)

        assert script._run(self._args()) == 1

    def test_a_transport_failure_exits_non_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def explode(*_: object) -> list[object]:
            raise httpx.ConnectError("no route to host")

        monkeypatch.setattr(script, "_probe", explode)

        assert script._run(self._args()) == 1

    def test_a_transport_failure_warns_against_reading_vendor_silence(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def explode(*_: object) -> list[object]:
            raise httpx.ConnectError("no route to host")

        monkeypatch.setattr(script, "_probe", explode)
        script._run(self._args())

        # The whole reason the probe exists: an unreachable origin and a
        # webhook KWS chose not to send are the same observation.
        assert "do not read a missing" in capsys.readouterr().out.lower()
