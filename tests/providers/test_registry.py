import asyncio
from typing import Any, AsyncIterator

import pytest

from agent_core.providers.auth import AuthSource, ProviderAuth
from agent_core.providers.registry import (
    MissingCredentialsError,
    ModelRegistry,
    UnknownProviderError,
)
from agent_core.providers.types import Model, StreamEvent


class FakeProvider:
    name = "fake"

    def list_models(self) -> list[Model]:
        return [
            Model(provider="fake", id="fast", context_window=1024, max_output_tokens=256),
            Model(provider="fake", id="slow", context_window=2048, max_output_tokens=512),
        ]

    async def stream(self, **kwargs: Any) -> AsyncIterator[StreamEvent]:
        if False:
            yield  # pragma: no cover


def test_register_and_find():
    reg = ModelRegistry()
    reg.register_provider(FakeProvider(), auth_source=AuthSource.static(api_key="k"))
    found = reg.find("fake", "fast")
    assert found is not None
    assert found.id == "fast"

    assert reg.find("fake", "missing") is None
    assert reg.find("unknown", "fast") is None


def test_list_available():
    reg = ModelRegistry()
    reg.register_provider(FakeProvider(), auth_source=AuthSource.static(api_key="k"))
    models = reg.list_available()
    assert {m.id for m in models} == {"fast", "slow"}


def test_get_auth():
    reg = ModelRegistry()
    reg.register_provider(FakeProvider(), auth_source=AuthSource.static(api_key="k"))
    model = reg.find("fake", "fast")
    auth = asyncio.run(reg.get_auth(model))
    assert auth.api_key == "k"


def test_get_auth_unknown_provider_raises():
    reg = ModelRegistry()
    model = Model(provider="ghost", id="x", context_window=1, max_output_tokens=1)
    with pytest.raises(UnknownProviderError):
        asyncio.run(reg.get_auth(model))


def test_get_provider():
    reg = ModelRegistry()
    p = FakeProvider()
    reg.register_provider(p, auth_source=AuthSource.static(api_key="k"))
    assert reg.get_provider("fake") is p
    with pytest.raises(UnknownProviderError):
        reg.get_provider("ghost")
