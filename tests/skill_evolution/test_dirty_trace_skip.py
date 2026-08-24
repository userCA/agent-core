"""Tests for legacy trace detection and analyze skip."""

from agent_core.skill_evolution.agent import is_legacy_user_query


def test_is_legacy_user_query_textcontent():
    assert is_legacy_user_query("[TextContent(type='text', text='hi')]")


def test_is_legacy_user_query_imagecontent():
    assert is_legacy_user_query("ImageContent(type='image', data='x')")


def test_is_legacy_user_query_clean():
    assert not is_legacy_user_query("帮我生成视频")
    assert not is_legacy_user_query("")
