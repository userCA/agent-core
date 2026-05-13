"""HTTP API tool adapter."""

from __future__ import annotations

import json
import os
from typing import Any, Callable

import httpx

from agent_core.core.content import TextContent
from agent_core.tools.base import ToolContext, ToolDefinition, ToolResult


class BearerAuth:
    def __init__(self, env_var: str | None = None, token: str | None = None) -> None:
        self.env_var = env_var
        self.token = token

    def resolve(self) -> str | None:
        if self.token:
            return self.token
        if self.env_var:
            return os.environ.get(self.env_var)
        return None


class HttpTool:
    def __init__(
        self,
        *,
        name: str,
        description: str,
        method: str,
        url: str,
        parameters: dict[str, Any],
        auth: BearerAuth | None = None,
        headers: dict[str, str] | None = None,
        request_template: dict[str, Any] | None = None,
        response_transform: Callable[[Any], Any] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.definition = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
        )
        self._method = method.upper()
        self._url = url
        self._auth = auth
        self._headers = headers or {}
        self._request_template = request_template
        self._response_transform = response_transform
        self._timeout = timeout

    async def execute(
        self,
        tool_call_id: str,
        params: dict[str, Any],
        ctx: ToolContext,
    ) -> ToolResult:
        req_headers = dict(self._headers)
        if self._auth:
            token = self._auth.resolve()
            if token:
                req_headers["Authorization"] = f"Bearer {token}"

        body = _render_template(self._request_template, params) if self._request_template else None

        url = self._url
        if self._method == "GET" and body is None:
            # Simple query parameter substitution for GET
            url = _render_url(url, params)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            if self._method == "GET":
                resp = await client.get(url, headers=req_headers)
            elif self._method == "POST":
                resp = await client.post(url, headers=req_headers, json=body or params)
            elif self._method == "PUT":
                resp = await client.put(url, headers=req_headers, json=body or params)
            elif self._method == "DELETE":
                resp = await client.delete(url, headers=req_headers)
            else:
                resp = await client.request(self._method, url, headers=req_headers, json=body or params)

            resp.raise_for_status()
            data = resp.json()

        if self._response_transform:
            data = self._response_transform(data)

        text = json.dumps(data, ensure_ascii=False, indent=2)
        return ToolResult(content=[TextContent(text=text)])


def _render_template(template: Any, params: dict[str, Any]) -> Any:
    if isinstance(template, str):
        return _substitute(template, params)
    if isinstance(template, dict):
        return {k: _render_template(v, params) for k, v in template.items()}
    if isinstance(template, list):
        return [_render_template(item, params) for item in template]
    return template


def _substitute(text: str, params: dict[str, Any]) -> str:
    result = text
    for key, value in params.items():
        placeholder = f"{{{{{key}}}}}"
        result = result.replace(placeholder, str(value))
    return result


def _render_url(url: str, params: dict[str, Any]) -> str:
    # Naive path parameter substitution
    result = url
    for key, value in params.items():
        placeholder = f"{{{key}}}"
        result = result.replace(placeholder, str(value))
    return result
