"""Provider credential resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Awaitable, Callable


class MissingCredentialsError(RuntimeError):
    """Raised when no credentials can be resolved for a provider."""


@dataclass
class ProviderAuth:
    api_key: str
    extra_headers: dict[str, str] | None = None


AuthCallback = Callable[[str], Awaitable[ProviderAuth]]


@dataclass
class AuthSource:
    _resolver: AuthCallback

    async def resolve(self, provider: str) -> ProviderAuth:
        return await self._resolver(provider)

    @classmethod
    def static(cls, *, api_key: str, extra_headers: dict[str, str] | None = None) -> "AuthSource":
        async def _cb(_: str) -> ProviderAuth:
            return ProviderAuth(api_key=api_key, extra_headers=extra_headers)

        return cls(_resolver=_cb)

    @classmethod
    def env(cls, var: str) -> "AuthSource":
        async def _cb(provider: str) -> ProviderAuth:
            value = os.environ.get(var)
            if not value:
                raise MissingCredentialsError(
                    f"Environment variable {var} not set for provider {provider}"
                )
            return ProviderAuth(api_key=value)

        return cls(_resolver=_cb)

    @classmethod
    def dynamic(cls, callback: AuthCallback) -> "AuthSource":
        return cls(_resolver=callback)
