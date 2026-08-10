from __future__ import annotations

import ast
import json
from types import SimpleNamespace
from typing import Any

from agent_core.workflows.errors import SandboxError

_FORBIDDEN_CALL_NAMES = frozenset({
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
})

_SAFE_BUILTINS = {
    "len": len,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "min": min,
    "max": max,
    "sum": sum,
    "sorted": sorted,
    "list": list,
    "dict": dict,
    "set": set,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "isinstance": isinstance,
    "type": type,
}


class _SandboxValidator(ast.NodeVisitor):
    def visit_Import(self, node: ast.Import) -> None:
        names = ", ".join(alias.name for alias in node.names)
        raise SandboxError(f"Import not allowed: {names}")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        raise SandboxError(f"Import not allowed: {module}")

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALL_NAMES:
            raise SandboxError(f"Call to forbidden function not allowed: {node.func.id}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__"):
            raise SandboxError(f"Dunder attribute access not allowed: {node.attr}")
        self.generic_visit(node)


def validate_workflow_source(source: str) -> ast.AST:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise SandboxError(f"Syntax error: {exc}") from exc

    _SandboxValidator().visit(tree)
    return tree


def build_sandbox_globals(
    ctx: Any,
    args: dict[str, Any],
    *,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    globals_dict: dict[str, Any] = {
        "ctx": ctx,
        "args": dict(args),
        "json": SimpleNamespace(dumps=json.dumps, loads=json.loads),
        **_SAFE_BUILTINS,
    }
    if extras:
        globals_dict.update(extras)
    return globals_dict
