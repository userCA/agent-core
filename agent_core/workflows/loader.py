from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_core.workflows.errors import SandboxError
from agent_core.workflows.sandbox import validate_workflow_source
from agent_core.workflows.types import WorkflowMeta

logger = logging.getLogger(__name__)

_RECIPES_DIR = Path(__file__).parent / "recipes"


@dataclass
class WorkflowSpec:
    meta: WorkflowMeta
    source: str
    path: str


class WorkflowLoader:
    """Discover and load workflow assets from search paths and builtin recipes."""

    def __init__(
        self,
        *,
        search_paths: list[str],
        include_builtin_recipes: bool = True,
    ) -> None:
        self._search_paths = search_paths
        self._include_builtin_recipes = include_builtin_recipes
        self._specs_by_name: dict[str, WorkflowSpec] | None = None
        self._invalid_names: set[str] = set()

    def list_names(self) -> list[str]:
        self._ensure_indexed()
        assert self._specs_by_name is not None
        return sorted(self._specs_by_name.keys())

    def get(self, name: str) -> WorkflowSpec:
        self._ensure_indexed()
        assert self._specs_by_name is not None
        if name in self._specs_by_name:
            return self._specs_by_name[name]
        if name in self._invalid_names:
            raise SandboxError(f"Workflow {name!r} failed validation")
        raise KeyError(name)

    def list_meta(self) -> list[WorkflowMeta]:
        self._ensure_indexed()
        assert self._specs_by_name is not None
        return [spec.meta for spec in self._specs_by_name.values()]

    def _ensure_indexed(self) -> None:
        if self._specs_by_name is not None:
            return
        self._specs_by_name = {}
        self._invalid_names = set()
        for path in self._discover_files():
            self._index_file(path)

    def _discover_files(self) -> list[Path]:
        files: list[Path] = []
        for search_path in self._search_paths:
            directory = Path(search_path)
            if directory.is_dir():
                files.extend(sorted(directory.glob("*.py")))
        if self._include_builtin_recipes and _RECIPES_DIR.is_dir():
            files.extend(sorted(_RECIPES_DIR.glob("*.py")))
        return files

    def _index_file(self, path: Path) -> None:
        source = ""
        try:
            source = path.read_text(encoding="utf-8")
            spec = _parse_workflow_spec(source, path)
        except Exception as exc:
            name = _resolve_name_from_source(source, path) if source else path.stem
            self._invalid_names.add(name)
            logger.warning("Skipping invalid workflow %s (%s): %s", path, name, exc)
            return

        existing = self._specs_by_name.get(spec.meta.name)
        if existing is not None:
            logger.warning(
                "Duplicate workflow name %r: %s overrides %s",
                spec.meta.name,
                path,
                existing.path,
            )
        self._specs_by_name[spec.meta.name] = spec


def _parse_workflow_spec(source: str, path: Path) -> WorkflowSpec:
    tree = validate_workflow_source(source)
    if not _has_async_run(tree):
        raise SandboxError("Workflow must define async def run(ctx)")
    meta = _extract_meta(tree, path.stem)
    return WorkflowSpec(meta=meta, source=source, path=str(path))


def _has_async_run(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run":
            args = node.args.args
            if args and args[0].arg == "ctx":
                return True
    return False


def _extract_meta(tree: ast.AST, fallback_name: str) -> WorkflowMeta:
    module = tree if isinstance(tree, ast.Module) else None
    if module is None:
        raise SandboxError("Expected module-level meta assignment")

    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "meta":
                if isinstance(node.value, ast.Dict):
                    meta_dict = _eval_literal(node.value)
                    if not isinstance(meta_dict, dict):
                        raise SandboxError("meta must be a dict literal")
                    if "name" not in meta_dict:
                        meta_dict = {**meta_dict, "name": fallback_name}
                    return WorkflowMeta.model_validate(meta_dict)
                if isinstance(node.value, ast.Call):
                    return _extract_meta_from_call(node.value, fallback_name)

    raise SandboxError("Workflow must export meta")


def _extract_meta_from_call(node: ast.Call, fallback_name: str) -> WorkflowMeta:
    func = node.func
    if isinstance(func, ast.Name) and func.id == "WorkflowMeta":
        kwargs: dict[str, Any] = {}
        for keyword in node.keywords:
            if keyword.arg is None:
                raise SandboxError("meta WorkflowMeta() does not support **kwargs spread")
            kwargs[keyword.arg] = _eval_literal(keyword.value)
        if "name" not in kwargs:
            kwargs["name"] = fallback_name
        return WorkflowMeta.model_validate(kwargs)
    raise SandboxError("Workflow must export meta as dict or WorkflowMeta(...)")


def _resolve_name_from_source(source: str, path: Path) -> str:
    try:
        tree = ast.parse(source)
        return _extract_meta(tree, path.stem).name
    except Exception:
        return path.stem


def _eval_literal(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Dict):
        return {
            _eval_literal(key): _eval_literal(value)
            for key, value in zip(node.keys, node.values)
            if key is not None
        }
    if isinstance(node, ast.List):
        return [_eval_literal(element) for element in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_eval_literal(element) for element in node.elts)
    if isinstance(node, ast.Name):
        if node.id == "True":
            return True
        if node.id == "False":
            return False
        if node.id == "None":
            return None
    raise SandboxError(f"Unsupported literal in meta: {type(node).__name__}")
