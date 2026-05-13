import asyncio
import os

import pytest

from agent_core.providers.auth import AuthSource, MissingCredentialsError, ProviderAuth


def test_static_auth():
    source = AuthSource.static(api_key="sk-test")
    auth = asyncio.run(source.resolve("openai"))
    assert auth.api_key == "sk-test"


def test_env_auth(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    source = AuthSource.env("OPENAI_API_KEY")
    auth = asyncio.run(source.resolve("openai"))
    assert auth.api_key == "sk-env"


def test_env_auth_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    source = AuthSource.env("OPENAI_API_KEY")
    with pytest.raises(MissingCredentialsError):
        asyncio.run(source.resolve("openai"))


def test_dynamic_auth():
    async def cb(provider: str) -> ProviderAuth:
        return ProviderAuth(api_key=f"sk-{provider}")

    source = AuthSource.dynamic(cb)
    auth = asyncio.run(source.resolve("openai"))
    assert auth.api_key == "sk-openai"
