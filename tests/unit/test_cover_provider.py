"""generate_cover_image calls nano banana and extracts image bytes."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cyo_adventure.covers.errors import CoverGenerationError
from cyo_adventure.covers.provider import generate_cover_image

pytestmark = pytest.mark.unit


def _settings(key="k"):
    return SimpleNamespace(gemini_api_key=key, cover_model="gemini-3-pro-image-preview")


def _response_with_image(data=b"IMG"):
    part = SimpleNamespace(
        inline_data=SimpleNamespace(data=data, mime_type="image/png")
    )
    content = SimpleNamespace(parts=[part])
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=content)], prompt_feedback=None
    )


def test_returns_first_inline_image():
    fake_client = SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **kw: _response_with_image())
    )
    with patch("cyo_adventure.covers.provider.genai.Client", return_value=fake_client):
        out = generate_cover_image("prompt", _settings())
    assert out == b"IMG"


def test_refusal_raises():
    empty = SimpleNamespace(candidates=[], prompt_feedback="blocked")
    fake_client = SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **kw: empty)
    )
    with (
        patch("cyo_adventure.covers.provider.genai.Client", return_value=fake_client),
        pytest.raises(CoverGenerationError),
    ):
        generate_cover_image("prompt", _settings())


def test_missing_key_raises():
    with pytest.raises(CoverGenerationError):
        generate_cover_image("prompt", _settings(key=None))


def _client_returning(response: SimpleNamespace) -> SimpleNamespace:
    """Build a fake genai client whose generate_content returns ``response``."""
    return SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **kw: response)
    )


@pytest.mark.unit
def test_generate_cover_image_empty_api_key_raises_without_client() -> None:
    """An empty-string API key fails fast and never constructs a client."""
    with (
        patch("cyo_adventure.covers.provider.genai.Client") as client_cls,
        pytest.raises(CoverGenerationError, match="GEMINI_API_KEY"),
    ):
        generate_cover_image("prompt", _settings(key=""))
    client_cls.assert_not_called()


@pytest.mark.unit
def test_generate_cover_image_none_candidates_raises_generation_error() -> None:
    """A response whose candidates attribute is None raises, not iterates."""
    response = SimpleNamespace(candidates=None, prompt_feedback=None)
    with (
        patch(
            "cyo_adventure.covers.provider.genai.Client",
            return_value=_client_returning(response),
        ),
        pytest.raises(CoverGenerationError),
    ):
        generate_cover_image("prompt", _settings())


@pytest.mark.unit
def test_generate_cover_image_candidate_without_content_raises_error() -> None:
    """A candidate whose content is None is skipped and the call raises."""
    response = SimpleNamespace(
        candidates=[SimpleNamespace(content=None)], prompt_feedback=None
    )
    with (
        patch(
            "cyo_adventure.covers.provider.genai.Client",
            return_value=_client_returning(response),
        ),
        pytest.raises(CoverGenerationError),
    ):
        generate_cover_image("prompt", _settings())


@pytest.mark.unit
def test_generate_cover_image_text_only_parts_raises_generation_error() -> None:
    """Parts with no inline_data (text-only reply) yield no image and raise."""
    part = SimpleNamespace(text="sorry, no image")
    response = SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))],
        prompt_feedback=None,
    )
    with (
        patch(
            "cyo_adventure.covers.provider.genai.Client",
            return_value=_client_returning(response),
        ),
        pytest.raises(CoverGenerationError),
    ):
        generate_cover_image("prompt", _settings())


@pytest.mark.unit
def test_generate_cover_image_empty_inline_data_raises_generation_error() -> None:
    """An inline image part with empty bytes is treated as no image."""
    response = _response_with_image(data=b"")
    with (
        patch(
            "cyo_adventure.covers.provider.genai.Client",
            return_value=_client_returning(response),
        ),
        pytest.raises(CoverGenerationError),
    ):
        generate_cover_image("prompt", _settings())


@pytest.mark.unit
def test_generate_cover_image_refusal_message_includes_prompt_feedback() -> None:
    """The raised error carries prompt_feedback so refusals are diagnosable."""
    response = SimpleNamespace(candidates=[], prompt_feedback="SAFETY_BLOCK")
    with (
        patch(
            "cyo_adventure.covers.provider.genai.Client",
            return_value=_client_returning(response),
        ),
        pytest.raises(CoverGenerationError, match="SAFETY_BLOCK"),
    ):
        generate_cover_image("prompt", _settings())


@pytest.mark.unit
def test_generate_cover_image_sdk_failure_propagates_unwrapped() -> None:
    """A transport-level SDK error propagates for the service layer to record."""

    def _boom(**kw: object) -> SimpleNamespace:
        msg = "gemini transport failure"
        raise ConnectionError(msg)

    client = SimpleNamespace(models=SimpleNamespace(generate_content=_boom))
    with (
        patch("cyo_adventure.covers.provider.genai.Client", return_value=client),
        pytest.raises(ConnectionError, match="gemini transport failure"),
    ):
        generate_cover_image("prompt", _settings())
