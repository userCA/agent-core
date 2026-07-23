"""Tests for path case store and top-k recall."""

from agent_core.skill_evolution.cases import (
    PathCase,
    append_case,
    format_cases_for_prompt,
    load_cases,
    select_top_k_cases,
)
from agent_core.skill_evolution.case_recall import SkillCaseRecallExtension
from agent_core.skill_evolution.types import PatchProposal
from agent_core.skill_evolution.validation import SkillValidationGate


def test_append_and_load_cases(tmp_path):
    skill = tmp_path / "demo"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: demo\n---\n# Demo\n", encoding="utf-8")
    append_case(
        tmp_path,
        PathCase(polarity="positive", query="fix bug", path="read → edit", skill_name="demo"),
    )
    append_case(
        tmp_path,
        PathCase(polarity="negative", query="fix bug", path="bash → bash", skill_name="demo"),
    )
    cases = load_cases(tmp_path, "demo")
    assert len(cases) == 2
    assert {c.polarity for c in cases} == {"positive", "negative"}


def test_select_top_k_prefers_overlap():
    cases = [
        PathCase(polarity="positive", query="unrelated topic", path="ls", skill_name="s"),
        PathCase(polarity="positive", query="fix type error bug", path="read → edit", skill_name="s"),
        PathCase(polarity="negative", query="fix bug with bash loop", path="bash", skill_name="s"),
    ]
    picked = select_top_k_cases("fix the bug", cases, k=2)
    assert len(picked) == 2
    assert all("bug" in c.query or "bug" in c.path for c in picked)


def test_format_cases_budget():
    cases = [
        PathCase(polarity="positive", query="q", path="a → b", skill_name="s"),
    ]
    text = format_cases_for_prompt(cases, max_chars=80)
    assert len(text) <= 80
    assert "Path Cases" in text or text.endswith("...")


async def test_apply_add_case_writes_jsonl(tmp_path):
    skill = tmp_path / "demo"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: demo\n---\n# Demo\n", encoding="utf-8")
    gate = SkillValidationGate(skill_dir=tmp_path, require_human_review=False)
    ok = await gate.apply_proposal(
        PatchProposal(
            proposal_id="p1",
            source_traces=["t1"],
            skill_name="demo",
            operation="add_case",
            case_polarity="positive",
            new_content="POSITIVE\nquery: fix bug\npath: read → edit\n",
        ),
        force=True,
    )
    assert ok is True
    cases = load_cases(tmp_path, "demo", polarity="positive")
    assert len(cases) == 1
    assert cases[0].query == "fix bug"
    assert "read" in cases[0].path


async def test_case_recall_extension_injects(tmp_path):
    append_case(
        tmp_path,
        PathCase(
            polarity="positive",
            query="fix authentication bug",
            path="read → edit",
            skill_name="demo",
        ),
    )
    ext = SkillCaseRecallExtension(
        skill_dir=tmp_path,
        skill_names=["demo"],
        top_k=1,
        enabled=True,
    )
    messages = [
        {"role": "system", "content": "base"},
        {"role": "user", "content": "please fix authentication bug"},
    ]
    out = await ext.transform_context(messages, None)
    joined = "\n".join(str(m.get("content", "")) for m in out)
    assert "Path Cases" in joined or "positive" in joined
