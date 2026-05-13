from pydantic import TypeAdapter

from agent_core.core.events import (
    AgentEnd,
    AgentEvent,
    AgentStart,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    TextDelta,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
    TurnStart,
)


def test_event_types_have_type_discriminator():
    assert AgentStart().type == "agent_start"
    assert AgentEnd(messages=[]).type == "agent_end"
    assert TurnStart().type == "turn_start"
    assert TurnEnd(message=None, tool_results=[]).type == "turn_end"
    assert MessageStart(message=None).type == "message_start"
    assert MessageEnd(message=None).type == "message_end"
    assert MessageUpdate(message=None, delta=TextDelta(text="hi")).type == "message_update"
    assert ToolExecutionStart(tool_call_id="x", tool_name="t", args={}).type == "tool_execution_start"
    assert ToolExecutionEnd(
        tool_call_id="x", tool_name="t", result=None, is_error=False
    ).type == "tool_execution_end"


def test_event_union_dispatch():
    adapter = TypeAdapter(AgentEvent)
    evt = adapter.validate_python({"type": "agent_start"})
    assert isinstance(evt, AgentStart)
