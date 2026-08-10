import json
from pathlib import Path

import pytest

from agent_core.workflows.errors import SandboxError
from agent_core.workflows.sandbox import build_sandbox_globals, validate_workflow_source

FIXTURES = Path(__file__).parent / "fixtures"

OK = """
async def run(ctx):
    await ctx.phase("p1")
    ctx.log("hi")
    return {"ok": True}
"""

BAD = """
import os
async def run(ctx):
    return os.getcwd()
"""

_FORBIDDEN_NAMES = frozenset({
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",
    "breakpoint",
    "getattr",
    "globals",
    "locals",
    "vars",
    "dir",
    "__builtins__",
})


def test_accepts_simple_async_run():
    validate_workflow_source(OK)


def test_rejects_import():
    with pytest.raises(SandboxError):
        validate_workflow_source(BAD)


def test_rejects_dunder_attr():
    src = """
async def run(ctx):
    return ctx.__class__
"""
    with pytest.raises(SandboxError):
        validate_workflow_source(src)


@pytest.mark.parametrize(
    "name",
    sorted(_FORBIDDEN_NAMES - {"__builtins__"}),
)
def test_rejects_forbidden_calls(name):
    src = f"""
async def run(ctx):
    {name}(ctx)
"""
    with pytest.raises(SandboxError):
        validate_workflow_source(src)


def test_fixture_ok_passes_validation():
    source = (FIXTURES / "sample_ok.py").read_text()
    validate_workflow_source(source)


def test_fixture_bad_import_fails_validation():
    source = (FIXTURES / "sample_bad_import.py").read_text()
    with pytest.raises(SandboxError):
        validate_workflow_source(source)


def test_build_sandbox_globals_injects_ctx_and_args():
    ctx = object()
    args = {"n": 2, "nested": {"k": "v"}}
    g = build_sandbox_globals(ctx, args)

    assert g["ctx"] is ctx
    assert g["args"] == args
    assert g["args"] is not args
    assert g["args"]["nested"] is args["nested"]


def test_build_sandbox_globals_excludes_dangerous_names():
    g = build_sandbox_globals(object(), {})

    assert "__builtins__" not in g
    assert _FORBIDDEN_NAMES.isdisjoint(g.keys())


def test_build_sandbox_globals_includes_safe_builtins_and_json():
    g = build_sandbox_globals(object(), {})

    assert g["len"]([1, 2]) == 2
    assert g["sorted"]([3, 1, 2]) == [1, 2, 3]
    assert g["json"].loads('{"a": 1}') == {"a": 1}
    assert g["json"].dumps({"a": 1}) == json.dumps({"a": 1})


def test_pattern_sandbox_extras_includes_all_helpers():
    from agent_core.workflows.sandbox import pattern_sandbox_extras

    extras = pattern_sandbox_extras()
    expected = {
        "fanout_synthesize",
        "adversarial_verify",
        "generate_and_filter",
        "tournament",
        "classify_and_execute",
        "loop_until",
    }
    assert expected <= set(extras.keys())
    assert all(callable(extras[name]) for name in expected)


def test_build_sandbox_globals_merges_extras():
    extra_fn = lambda x: x + 1
    g = build_sandbox_globals(object(), {}, extras={"inc": extra_fn})

    assert g["inc"](1) == 2
