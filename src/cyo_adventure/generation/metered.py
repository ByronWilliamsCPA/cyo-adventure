"""Usage-recording provider wrapper.

Wraps any provider and appends each call's usage to a run-scoped
:class:`~cyo_adventure.generation.usage.UsageLedger`, so accounting is
structural rather than conventional: a code path holding a
:class:`MeteredProvider` cannot make an unmetered call.

Composes exactly like
:class:`~cyo_adventure.generation.guarded.PiiGuardedProvider`, and satisfies
both the ``GenerationProvider`` and ``ReviewProvider`` structural protocols,
which declare the same ``complete`` coroutine. In practice the guard ends up
OUTSIDE this wrapper, because ``generate_story``/``fill_skeleton`` construct
their own guard around whatever provider they are handed. That is the ordering
the accounting wants: a prompt the guard rejects never reaches the meter, so it
correctly records no call. It made none.

Usage::

    ledger = UsageLedger()
    metered = MeteredProvider(build_provider(settings), ledger=ledger)
    ...
    totals = ledger.snapshot()

This wrapper deliberately writes nothing to the database, so no provider call
carries a database round-trip on its hot path; the worker stamps the aggregate
onto the job row once, at the end. The ledger nonetheless retains every call in
order rather than folding as it goes, which is what leaves a per-call event log
possible later without changing anything here. Nothing writes one today: the
persisted record is the per-job aggregate on ``generation_job``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

from cyo_adventure.generation.usage import Completion, TokenUsage

if TYPE_CHECKING:
    from cyo_adventure.generation.provider import GenerationProvider
    from cyo_adventure.generation.usage import UsageLedger

#: Attributes forwarded to the wrapped provider by name, preserving whether
#: the inner provider declares them at all. A caller distinguishes "this is not
#: a cascade" from "this cascade has not answered yet" by presence versus
#: value, so forwarding a value for an inner provider that has no such
#: attribute would erase that distinction. See :meth:`MeteredProvider.__getattr__`.
_FORWARDED_ATTRS: Final[frozenset[str]] = frozenset({"resolved_provider"})

__all__ = ["MeteredProvider", "ledger_of"]


class MeteredProvider:
    """Records each call's usage into a ledger, then forwards the response.

    Args:
        inner: The provider to delegate to.
        ledger: The run-scoped accumulator to append to. One per job; sharing
            one across concurrent jobs would cross-bill them.
    """

    def __init__(self, inner: GenerationProvider, *, ledger: UsageLedger) -> None:
        self._inner = inner
        self._ledger = ledger

    @property
    def ledger(self) -> UsageLedger:
        """The ledger this wrapper appends to.

        Exposed so a caller holding only the provider can read the run's
        accounting back. That is what lets the worker stamp usage from every
        path that already threads the provider (including its interrupt
        guard) without threading a second argument through each one.

        Returns:
            The run-scoped ledger passed at construction, not a copy: reading
            it mid-run gives the calls made so far.
        """
        return self._ledger

    # #CRITICAL: data-integrity: `name` and `model` are forwarded because the
    # worker stamps job.provider/job.model from them via
    # `getattr(provider, "name", None) or <configured default>`. A wrapper that
    # did not forward them would not fail; it would silently relabel every job
    # with the configured default, so an audit of which provider ran a job
    # would read the config rather than the run. A blanket `__getattr__` is
    # deliberately not used, since it would also forward typos; anything else
    # the codebase reads off a provider must be named in `_FORWARDED_ATTRS`.
    # #VERIFY: test_the_wrapper_forwards_the_provider_and_model_labels,
    # test_absent_labels_are_forwarded_as_none.

    @property
    def name(self) -> str | None:
        """The inner provider's name, or ``None`` when it declares none.

        Returns:
            The wrapped provider's ``name``, so the wrapper is invisible to
            the worker's provider labelling.
        """
        inner_name: object = getattr(self._inner, "name", None)
        return inner_name if isinstance(inner_name, str) else None

    @property
    def model(self) -> str | None:
        """The inner provider's model id, or ``None`` when it declares none.

        Returns:
            The wrapped provider's ``model``, forwarded for the same reason as
            :attr:`name`.
        """
        inner_model: object = getattr(self._inner, "model", None)
        return inner_model if isinstance(inner_model, str) else None

    # #CRITICAL: security: `resolved_provider` is forwarded because
    # moderation/pipeline.py judges reviewer independence on the backend that
    # ACTUALLY answered. A cascade reports the answering leg there and `None`
    # before any leg has answered, while its `name` is a composite label
    # ("fallback[...]") that equals no configured backend. A wrapper that
    # swallowed the attribute would make the pipeline read `name` instead, so
    # "different backend" would be unconditionally true and every metered
    # cascade run would persist `reviewer_independent=True` whatever answered:
    # a model could review its own output while the report attested it had not.
    # Forwarding by `__getattr__` (rather than a property) is what preserves
    # ABSENCE: a wrapped non-cascade provider must still look like it has no
    # `resolved_provider`, because the pipeline reads presence to decide
    # whether the provider's own `name` may speak for it.
    # #VERIFY: tests/unit/test_review_metering.py::
    # test_a_metered_cascade_is_judged_on_the_leg_that_answered and
    # ::test_metering_does_not_invent_a_resolution_for_a_plain_provider.

    def __getattr__(self, item: str) -> object:
        """Forward the small set of provider attributes named in `_FORWARDED_ATTRS`.

        Called only when normal attribute lookup fails, so it never shadows
        ``ledger``, ``name``, ``model``, or ``complete``.

        Args:
            item: The attribute name being looked up.

        Returns:
            The inner provider's value for a forwarded attribute.

        Raises:
            AttributeError: If the attribute is not forwarded, or the inner
                provider does not declare it. Raising here is load-bearing:
                it is what lets a caller tell a wrapped non-cascade provider
                apart from a cascade that has not answered.
        """
        if item in _FORWARDED_ATTRS:
            return getattr(self._inner, item)
        msg = f"{type(self).__name__!r} object has no attribute {item!r}"
        raise AttributeError(msg)

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int
    ) -> Completion:
        """Delegate to the inner provider and record what the call consumed.

        Args:
            system: System-role instructions block.
            prompt: User-role prompt block.
            max_tokens: Upper bound on response length in tokens.

        Returns:
            The inner provider's response, forwarded unchanged.
        """
        # #CRITICAL: data-integrity: accounting must never convert a degraded
        # response into an outage. Both provider protocols are structural, so
        # a non-conforming implementation can return anything, and the
        # moderation stages already rely on being handed exactly what the
        # backend produced so their own fail-safe paths can see it (see
        # moderation/review_provider.completion_text). Binding through
        # `object` keeps both guards below live under strict type checking; a
        # `Completion` annotation would let the checker prove them dead and a
        # later edit would remove them, which turns an unmetered call into a
        # crash on the response path.
        # #VERIFY: test_a_non_completion_response_is_forwarded_unmetered,
        # test_a_completion_with_a_non_usage_payload_is_forwarded_unmetered.
        returned: object = cast(
            "object",
            await self._inner.complete(
                system=system, prompt=prompt, max_tokens=max_tokens
            ),
        )
        if isinstance(returned, Completion):
            usage = cast("object", returned.usage)
            if isinstance(usage, TokenUsage):
                self._ledger.record(usage)
        return cast("Completion", returned)


def ledger_of(provider: object) -> UsageLedger | None:
    """Return the ledger a provider meters into, if it meters at all.

    Lets a function that already receives a provider reach the run's ledger
    without a second parameter threaded through every caller in between. The
    alternative considered and rejected was an ambient
    :class:`~contextvars.ContextVar`: an unset one drops usage silently, and
    silent under-counting is the failure this whole subsystem exists to make
    impossible.

    Detection is OUTERMOST-ONLY: the meter is found only when ``provider`` is
    itself a :class:`MeteredProvider`, never when one sits under another
    wrapper. Today every caller passes the provider it was handed, so the
    result is correct; a caller that wrapped it first (in its own
    ``PiiGuardedProvider``, say) would get ``None``, make unmetered calls, and
    raise no error. That is exactly the silent under-count named above, so the
    constraint is stated here rather than left to be rediscovered.

    Args:
        provider: A provider. Metering is detected only at the outermost
            layer, so pass the provider before wrapping it, not after.

    Returns:
        The ledger when ``provider`` is a :class:`MeteredProvider`, else
        ``None``, meaning this run is not being metered and a caller should
        make its calls exactly as it did before.
    """
    return provider.ledger if isinstance(provider, MeteredProvider) else None
