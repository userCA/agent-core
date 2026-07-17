from agent_core.core.state import AgentHarnessPhase, AgentState


def test_default_state():
    s = AgentState()
    assert s.system_prompt == ""
    assert s.model is None
    assert s.thinking_level == "off"
    assert s.tools == []
    assert s.messages == []
    assert s.phase == AgentHarnessPhase.IDLE
    assert s.is_streaming is False


def test_phase_enum_values():
    assert AgentHarnessPhase.IDLE.value == "idle"
    assert AgentHarnessPhase.TURN.value == "turn"
    assert AgentHarnessPhase.COMPACTION.value == "compaction"
    assert AgentHarnessPhase.BRANCH_SUMMARY.value == "branch_summary"
    assert AgentHarnessPhase.RETRY.value == "retry"


def test_phase_assignment():
    s = AgentState()
    s.phase = AgentHarnessPhase.TURN
    assert s.phase == AgentHarnessPhase.TURN
    assert s.phase.value == "turn"


def test_assignment_copies_lists():
    s = AgentState()
    tools_in = [{"name": "x"}]
    s.tools = tools_in
    tools_in.append({"name": "y"})
    assert len(s.tools) == 1  # outer list copy isolates external mutation
