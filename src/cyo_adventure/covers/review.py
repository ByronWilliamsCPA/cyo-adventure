"""Independent vision-model review of a generated cover, before upload.

One LLM call per generation attempt, judging a cover's raw bytes against the
exact prompt covers/prompt.py::build_cover_prompt produced for the generator.
Mirrors moderation/fidelity_review.py::run_semantic_fidelity_check's shape (a
pass/flag JSON verdict, fail-open on anything unparseable) with a
vision-capable model in place of a text-only one.

See docs/superpowers/specs/2026-09-08-cover-ai-review-design.md Design
section 1, and this plan's Codebase Discovery Summary for the one deliberate
deviation from the fidelity_review.py precedent: a ProviderError from the
review call is caught HERE (not left to propagate), because
covers/service.py::generate_cover's outer exception handler would otherwise
turn a transient reviewer outage into a failed cover generation.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Protocol

from cyo_adventure.core.exceptions import ProviderError
from cyo_adventure.moderation.review_provider import completion_text
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from cyo_adventure.generation.usage import Completion

logger = get_logger(__name__)

# Short JSON verdict + a one-sentence note; no reasoning is expected or wanted.
_MAX_REVIEW_TOKENS = 512

_SYSTEM_PROMPT = (
    "You are reviewing an AI-generated book cover image against the prompt "
    "the artist was given. Flag the cover if EITHER is true: "
    "(1) the image contains any visible text, letters, numbers, or logos "
    "anywhere in it (the artist was explicitly told to render none), or "
    "(2) the art does not plausibly depict the scene, subject, or characters "
    "described in the prompt (wrong species, wrong setting, garbled or "
    "unrelated imagery). Respond with ONLY a JSON object of the exact shape "
    '{"verdict": "pass" | "flag", "notes": "<short reason, or empty if pass>"}. '
    "No other text."
)


class ImageReviewProvider(Protocol):
    """The subset of a review provider that ``review_cover`` needs.

    Deliberately narrower than moderation.review_provider.ReviewProvider,
    which stays complete()-only so every existing text reviewer and every
    existing mock keeps working unchanged (spec Design section 2). Only the
    OpenRouter-backed provider and MockProvider implement this method.
    """

    async def complete_with_image(  # noqa: PLR0913
        self,
        *,
        system: str,
        prompt: str,
        image_bytes: bytes,
        image_mime: str,
        max_tokens: int,
    ) -> Completion:
        """Return the model's completion for a system+user+image input."""
        ...


async def review_cover(
    image_bytes: bytes,
    generation_prompt: str,
    review_provider: ImageReviewProvider,
    *,
    image_mime: str = "image/png",
) -> tuple[str | None, str | None]:
    """Ask an independent vision model whether a cover matches its prompt.

    Args:
        image_bytes: The raw (pre-optimize) cover image bytes to review.
        generation_prompt: The exact prompt covers.prompt.build_cover_prompt
            produced for the generator; embedded as "what the artist was
            asked to draw" so the reviewer judges subject-coherence against
            it, not a bare protagonist name.
        review_provider: A provider implementing complete_with_image().
        image_mime: The image's MIME type; covers/provider.py returns PNG
            bytes today, so this defaults to "image/png".

    Returns:
        (verdict, notes): verdict is "pass", "flag", or None (a
        ProviderError, an unparseable/empty response, or a value outside
        {"pass", "flag"} -- all treated as pass by the caller); notes is the
        reviewer's short explanation, or None when none was returned.
    """
    user_prompt = (
        "Here is what the artist was asked to draw:\n\n"
        f"{generation_prompt}\n\n"
        "Review the attached image against these instructions."
    )
    # #CRITICAL: external resources: the review call is a network-backed vision-LLM
    # request with no guaranteed availability; this module's whole design is
    # fail-open (module docstring), so a provider outage must degrade to
    # verdict=None (treated as pass upstream), never propagate and fail the
    # cover generation it is reviewing.
    # #VERIFY: covers/service.py::generate_cover treats a None verdict as pass.
    try:
        completion = await review_provider.complete_with_image(
            system=_SYSTEM_PROMPT,
            prompt=user_prompt,
            image_bytes=image_bytes,
            image_mime=image_mime,
            max_tokens=_MAX_REVIEW_TOKENS,
        )
    except ProviderError:
        logger.warning("cover_review_call_failed", exc_info=True)
        return None, None
    text = completion_text(completion)
    if not text:
        return None, None
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None, None
    if not isinstance(parsed, dict):
        return None, None
    # #ASSUME: data integrity: `parsed["verdict"]` is untrusted model output, not
    # a guaranteed literal "pass"/"flag" token; a model that returns "Flag" or
    # "flag " (case or whitespace noise) must still be recognized as a flag, not
    # silently fall through to the None-treated-as-pass path below.
    # #VERIFY: test_review_cover_flag_verdict_is_case_and_whitespace_insensitive.
    raw_verdict = parsed.get("verdict")
    verdict = raw_verdict.strip().lower() if isinstance(raw_verdict, str) else None
    if verdict not in ("pass", "flag"):
        return None, None
    notes = parsed.get("notes")
    return verdict, (notes if isinstance(notes, str) else None)
