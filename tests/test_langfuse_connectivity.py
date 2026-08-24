"""Verify local network access to the self-hosted Langfuse instance.

Target: http://36.133.115.210:8888/proxy_name/langfuse

These tests confirm TCP connectivity, HTTP reachability, and OTLP endpoint
availability from the developer's machine.  They are **not** part of the
regular CI suite — run manually when diagnosing Langfuse connectivity.

Usage::

    pytest tests/test_langfuse_connectivity.py -v
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

LANGFUSE_BASE = "http://36.133.115.210:8888/proxy_name/langfuse"
TIMEOUT = 10  # seconds


def _get(path: str, *, method: str = "GET") -> tuple[int, str, bytes]:
    """Issue an HTTP request and return (status, content_type, body)."""
    url = f"{LANGFUSE_BASE}{path}"
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            ct = resp.headers.get("Content-Type", "")
            body = resp.read()
            return resp.status, ct, body
    except urllib.error.HTTPError as e:
        ct = e.headers.get("Content-Type", "") if e.headers else ""
        body = e.read() if hasattr(e, "read") else b""
        return e.code, ct, body
    except Exception as exc:
        pytest.fail(f"Request to {url} failed: {exc}")


# -- Tests ------------------------------------------------------------------


class TestLangfuseConnectivity:
    """Network-level checks for the self-hosted Langfuse instance."""

    def test_homepage_reachable(self):
        """Langfuse root page returns 200 with HTML content."""
        status, ct, body = _get("/")
        assert status == 200, f"Expected 200, got {status}"
        assert "text/html" in ct
        assert len(body) > 100, "Homepage body unexpectedly small"

    def test_sign_in_page_reachable(self):
        """Login page is accessible for manual browser verification."""
        status, ct, body = _get("/auth/sign-in")
        assert status == 200
        assert "text/html" in ct
        assert len(body) > 100

    def test_health_endpoint_ok(self):
        """/api/public/health returns 200 with JSON payload."""
        status, ct, body = _get("/api/public/health")
        assert status == 200, f"Health check failed: {status}"
        assert "application/json" in ct
        data = json.loads(body)
        assert isinstance(data, dict)

    def test_otlp_traces_endpoint_exists(self):
        """OTLP traces endpoint exists (405 = method not allowed for GET,
        meaning POST is accepted — which is what OTLP exporters use)."""
        status, ct, _ = _get("/api/public/otel/v1/traces")
        assert status == 405, (
            f"Expected 405 (POST-only), got {status}. "
            "OTLP endpoint may not be configured at this path."
        )
        assert "application/json" in ct

    def test_otlp_traces_post_accepted(self):
        """OTLP traces endpoint accepts POST with empty body (returns 4xx, not 404)."""
        url = f"{LANGFUSE_BASE}/api/public/otel/v1/traces"
        data = b""
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/x-protobuf"},
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                status = resp.status
        except urllib.error.HTTPError as e:
            status = e.code

        # 400/401/422 = endpoint exists and parsed the (empty) body
        # 404 = endpoint missing
        assert status != 404, "OTLP POST endpoint returned 404 — path may be wrong"
        assert status < 500, f"Server error {status} on OTLP endpoint"
