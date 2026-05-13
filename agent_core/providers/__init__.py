"""Provider abstractions and built-in adapters."""

from agent_core.providers.auth import (
    AuthSource,
    MissingCredentialsError,
    ProviderAuth,
)
from agent_core.providers.base import ModelProvider
from agent_core.providers.openai_provider import OpenAIProvider
from agent_core.providers.registry import ModelRegistry, UnknownProviderError
from agent_core.providers.types import (
    Model,
    ModelCost,
    StreamEvent,
    StreamMessageEnd,
    StreamTextDelta,
    StreamThinkingDelta,
    StreamToolCallDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
)

__all__ = [
    "AuthSource",
    "MissingCredentialsError",
    "ProviderAuth",
    "ModelProvider",
    "Model",
    "ModelCost",
    "ModelRegistry",
    "OpenAIProvider",
    "StreamEvent",
    "StreamMessageEnd",
    "StreamTextDelta",
    "StreamThinkingDelta",
    "StreamToolCallDelta",
    "StreamToolCallEnd",
    "StreamToolCallStart",
    "UnknownProviderError",
]
