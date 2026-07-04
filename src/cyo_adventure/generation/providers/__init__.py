"""Live ``GenerationProvider`` adapters and the composite fallback cascade.

This subpackage holds the concrete LLM-backend adapters that perform real
network I/O, separated from the ``GenerationProvider`` protocol, ``MockProvider``
test double, and ``build_provider`` factory in
:mod:`cyo_adventure.generation.provider`.

Each adapter satisfies the ``GenerationProvider`` protocol structurally (no
inheritance) and maps backend failures to
:class:`~cyo_adventure.core.exceptions.ProviderError`. The
:class:`~cyo_adventure.generation.providers.fallback.FallbackProvider` composes
adapters into an ordered cascade with cross-leg failover.
"""

from __future__ import annotations

from cyo_adventure.generation.providers.fallback import FallbackProvider
from cyo_adventure.generation.providers.modal import ModalProvider
from cyo_adventure.generation.providers.ollama import OllamaProvider
from cyo_adventure.generation.providers.openrouter import OpenRouterProvider

__all__ = [
    "FallbackProvider",
    "ModalProvider",
    "OllamaProvider",
    "OpenRouterProvider",
]
