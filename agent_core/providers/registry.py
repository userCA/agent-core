"""ModelRegistry — maps provider name → ModelProvider + credentials."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_core.providers.auth import (
    AuthSource,
    MissingCredentialsError,
    ProviderAuth,
)
from agent_core.providers.base import ModelProvider
from agent_core.providers.types import Model


class UnknownProviderError(KeyError):
    """Raised when a provider name is not registered."""


@dataclass
class _Entry:
    provider: ModelProvider
    auth_source: AuthSource
    models: dict[str, Model] = field(default_factory=dict)


class ModelRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}

    def register_provider(
        self, provider: ModelProvider, *, auth_source: AuthSource
    ) -> None:
        models = {m.id: m for m in provider.list_models()}
        self._entries[provider.name] = _Entry(
            provider=provider, auth_source=auth_source, models=models
        )

    def get_provider(self, name: str) -> ModelProvider:
        entry = self._entries.get(name)
        if entry is None:
            raise UnknownProviderError(name)
        return entry.provider

    def find(self, provider: str, model_id: str) -> Model | None:
        entry = self._entries.get(provider)
        if entry is None:
            return None
        return entry.models.get(model_id)

    def list_available(self) -> list[Model]:
        return [m for entry in self._entries.values() for m in entry.models.values()]

    async def get_auth(self, model: Model) -> ProviderAuth:
        entry = self._entries.get(model.provider)
        if entry is None:
            raise UnknownProviderError(model.provider)
        return await entry.auth_source.resolve(model.provider)

    def has_configured_auth(self, model: Model) -> bool:
        return model.provider in self._entries


__all__ = [
    "ModelRegistry",
    "UnknownProviderError",
    "MissingCredentialsError",
]
