from agent_core.core.state import AgentState


def test_default_state():
    s = AgentState()
    assert s.system_prompt == ""
    assert s.model is None
    assert s.thinking_level == "off"
    assert s.tools == []
    assert s.messages == []
    assert s.is_streaming is False


def test_assignment_copies_lists():
    s = AgentState()
    tools_in = [{"name": "x"}]
    s.tools = tools_in
    tools_in.append({"name": "y"})
    assert len(s.tools) == 1  # outer list copy isolates external mutation
