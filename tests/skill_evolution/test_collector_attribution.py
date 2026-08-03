"""Tests for SkillTraceCollector attribution and query extraction."""

from agent_core.core.content import TextContent
from agent_core.core.events import (
    AgentStart,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
)
from agent_core.extensions.base import ExtensionContext
from agent_core.resources.types import Skill, SourceInfo
from agent_core.skill_evolution.collector import SkillTraceCollector
from agent_core.skill_evolution.store import InMemorySkillEvolutionStore


def _skill(name: str, tools: list[str] | None = None) -> Skill:
    return Skill(
        name=name,
        description="demo skill",
        content="## 规则 1：Always verify\n",
        source=SourceInfo(
            source="project",
            scope="project",
            origin=f"/tmp/{name}/SKILL.md",
            base_dir=f"/tmp/{name}",
        ),
        tools=tools or [],
    )


class _FakeMessage:
    error_message = None
    stop_reason = "stop"


async def test_extract_text_from_textcontent_list():
    text = SkillTraceCollector._extract_text_from_content(
        [TextContent(text="生成一个视频")]
    )
    assert text == "生成一个视频"


async def test_tool_activation_attributes_single_skill():
    store = InMemorySkillEvolutionStore()
    collector = SkillTraceCollector(store)
    collector.register_skills([_skill("image-generation", tools=["nolo_video"])])

    class FakeState:
        system_prompt = (
            "<available_skills>\n"
            '  <skill name="image-generation">desc</skill>\n'
            '  <skill name="code-review">desc</skill>\n'
            "</available_skills>"
        )
        messages = [type("U", (), {"role": "user", "content": "生成视频"})()]

    ctx = ExtensionContext(session_id="s1", harness=type("A", (), {"state": FakeState()})(), store=store)

    await collector.on_event(ctx, AgentStart())
    await collector.on_event(
        ctx,
        ToolExecutionStart(tool_call_id="c1", tool_name="nolo_video", args={}),
    )
    await collector.on_event(
        ctx,
        ToolExecutionEnd(tool_call_id="c1", tool_name="nolo_video", result="ok", is_error=False),
    )
    await collector.on_event(ctx, TurnEnd(message=_FakeMessage(), tool_results=[]))

    traces = await store.get_traces()
    assert len(traces) == 1
    assert traces[0].skill_name == "image-generation"
    assert traces[0].user_query == "生成视频"
    assert traces[0].loaded_rules == ["rule_1"]


async def test_multiple_available_skills_without_activation_skips_trace():
    store = InMemorySkillEvolutionStore()
    collector = SkillTraceCollector(store)
    collector.register_skills([
        _skill("image-generation"),
        _skill("code-review"),
    ])

    class FakeState:
        system_prompt = (
            "<available_skills>\n"
            '  <skill name="image-generation">desc</skill>\n'
            '  <skill name="code-review">desc</skill>\n'
            "</available_skills>"
        )
        messages = []

    ctx = ExtensionContext(session_id="s1", harness=type("A", (), {"state": FakeState()})(), store=store)
    await collector.on_event(ctx, AgentStart())
    await collector.on_event(ctx, TurnEnd(message=_FakeMessage(), tool_results=[]))

    traces = await store.get_traces()
    assert traces == []


async def test_step_errors_mark_failure_outcome():
    store = InMemorySkillEvolutionStore()
    collector = SkillTraceCollector(store)
    collector.register_skills([_skill("demo", tools=["broken_tool"])])

    class FakeState:
        system_prompt = (
            "<available_skills>\n"
            '  <skill name="demo">desc</skill>\n'
            "</available_skills>"
        )
        messages = [type("U", (), {"role": "user", "content": "run"})()]

    ctx = ExtensionContext(session_id="s1", harness=type("A", (), {"state": FakeState()})(), store=store)
    await collector.on_event(ctx, AgentStart())
    await collector.on_event(
        ctx,
        ToolExecutionStart(tool_call_id="c1", tool_name="broken_tool", args={}),
    )
    await collector.on_event(
        ctx,
        ToolExecutionEnd(
            tool_call_id="c1",
            tool_name="broken_tool",
            result="Tool not found",
            is_error=True,
        ),
    )
    await collector.on_event(ctx, TurnEnd(message=_FakeMessage(), tool_results=[]))

    traces = await store.get_traces()
    assert len(traces) == 1
    assert traces[0].execution_outcome.value == "failure"
