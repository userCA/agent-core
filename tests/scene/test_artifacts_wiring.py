"""Tests for Scene L1 artifact wiring."""

from __future__ import annotations

import pytest

import scene.http_sse.artifacts_config as artifacts_config
from scene.http_sse.artifacts_config import (
    artifacts_enabled,
    build_artifact_extension,
    shared_artifact_store,
)


@pytest.fixture(autouse=True)
def _reset_shared_store():
    artifacts_config._SHARED_STORE = None
    yield
    artifacts_config._SHARED_STORE = None


def test_artifacts_enabled_default(monkeypatch):
    monkeypatch.delenv("ENABLE_ARTIFACTS", raising=False)
    assert artifacts_enabled() is True


def test_artifacts_disabled(monkeypatch):
    for val in ("0", "false", "off", "no"):
        monkeypatch.setenv("ENABLE_ARTIFACTS", val)
        assert artifacts_enabled() is False
        store, ext = build_artifact_extension()
        assert store is None and ext is None


def test_shared_artifact_store_singleton():
    a = shared_artifact_store()
    b = shared_artifact_store()
    assert a is b


def test_build_artifact_extension_default(monkeypatch):
    monkeypatch.setenv("ENABLE_ARTIFACTS", "1")
    monkeypatch.delenv("ARTIFACT_CHAR_THRESHOLD", raising=False)
    monkeypatch.delenv("ARTIFACT_SUMMARY_CHARS", raising=False)
    store, ext = build_artifact_extension()
    assert store is not None
    assert ext is not None
    assert ext.name == "artifact_externalize"
    assert store is shared_artifact_store()
    assert ext._char_threshold == 4000
    assert ext._summary_chars == 3500


def test_artifact_threshold_env(monkeypatch):
    monkeypatch.setenv("ENABLE_ARTIFACTS", "1")
    monkeypatch.setenv("ARTIFACT_CHAR_THRESHOLD", "100")
    monkeypatch.setenv("ARTIFACT_SUMMARY_CHARS", "20")
    _, ext = build_artifact_extension()
    assert ext is not None
    assert ext._char_threshold == 100
    assert ext._summary_chars == 20


def test_artifact_threshold_invalid_env_falls_back(monkeypatch):
    monkeypatch.setenv("ENABLE_ARTIFACTS", "1")
    monkeypatch.setenv("ARTIFACT_CHAR_THRESHOLD", "nope")
    monkeypatch.setenv("ARTIFACT_SUMMARY_CHARS", "-5")
    _, ext = build_artifact_extension()
    assert ext is not None
    assert ext._char_threshold == 4000
    assert ext._summary_chars == 3500
