from pathlib import Path

import pytest

from agent_core.workflows.errors import SandboxError
from agent_core.workflows.loader import WorkflowLoader

FIXTURES = Path(__file__).parent / "fixtures"

SAMPLE_OK = '''\
meta = {
    "name": "sample-ok",
    "description": "Sample OK workflow",
    "phases": ["p1"],
}


async def run(ctx):
    await ctx.phase("p1")
    ctx.log("hi")
    return {"ok": True}
'''

SAMPLE_BAD = '''\
meta = {
    "name": "sample-bad-import",
    "description": "Workflow with forbidden import",
}

import os


async def run(ctx):
    return os.getcwd()
'''


def test_loader_lists_and_gets_tmp_path_workflow(tmp_path):
    (tmp_path / "sample_ok.py").write_text(SAMPLE_OK, encoding="utf-8")

    loader = WorkflowLoader(search_paths=[str(tmp_path)], include_builtin_recipes=False)
    names = loader.list_names()

    assert names == ["sample-ok"]
    spec = loader.get("sample-ok")
    assert spec.meta.name == "sample-ok"
    assert spec.meta.description == "Sample OK workflow"
    assert spec.meta.phases == ["p1"]
    assert "async def run" in spec.source
    assert spec.path.endswith("sample_ok.py")


def test_loader_skips_invalid_in_list_and_raises_on_get(tmp_path):
    (tmp_path / "sample_ok.py").write_text(SAMPLE_OK, encoding="utf-8")
    (tmp_path / "sample_bad_import.py").write_text(SAMPLE_BAD, encoding="utf-8")

    loader = WorkflowLoader(search_paths=[str(tmp_path)], include_builtin_recipes=False)
    names = loader.list_names()

    assert names == ["sample-ok"]
    assert "sample-bad-import" not in names

    with pytest.raises(SandboxError):
        loader.get("sample-bad-import")


def test_loader_get_missing_raises_key_error(tmp_path):
    loader = WorkflowLoader(search_paths=[str(tmp_path)], include_builtin_recipes=False)

    with pytest.raises(KeyError):
        loader.get("missing-workflow")


def test_loader_loads_fixture_sample_ok():
    loader = WorkflowLoader(
        search_paths=[str(FIXTURES)],
        include_builtin_recipes=False,
    )

    names = loader.list_names()
    assert "sample-ok" in names

    spec = loader.get("sample-ok")
    assert spec.meta.name == "sample-ok"
    assert "async def run" in spec.source
    assert spec.path.endswith("sample_ok.py")


def test_list_meta_returns_workflow_meta_objects(tmp_path):
    (tmp_path / "sample_ok.py").write_text(SAMPLE_OK, encoding="utf-8")

    loader = WorkflowLoader(search_paths=[str(tmp_path)], include_builtin_recipes=False)
    metas = loader.list_meta()

    assert len(metas) == 1
    assert metas[0].name == "sample-ok"
    assert metas[0].phases == ["p1"]


def test_loader_lists_builtin_recipes(tmp_path):
    loader = WorkflowLoader(search_paths=[str(tmp_path)], include_builtin_recipes=True)
    names = loader.list_names()

    assert "fanout-synthesize" in names
    assert "adversarial-review" in names

    fanout = loader.get("fanout-synthesize")
    assert fanout.meta.phases == ["fanout", "synthesize"]

    review = loader.get("adversarial-review")
    assert review.meta.phases == ["verify"]
