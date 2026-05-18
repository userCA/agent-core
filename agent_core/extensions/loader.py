"""Dynamic extension loading from modules and entry points."""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
from typing import Any

from agent_core.extensions.base import Extension
from agent_core.resources.diagnostics import ResourceDiagnostics
from agent_core.resources.types import ExtensionSpec

logger = logging.getLogger(__name__)


class ExtensionLoader:
    """Load extensions from module paths and entry points."""

    def load_from_specs(self, specs: list[ExtensionSpec]) -> list[Extension]:
        extensions: list[Extension] = []
        for spec in specs:
            try:
                ext = self._load_spec(spec)
                if ext is not None:
                    extensions.append(ext)
            except Exception as exc:
                logger.warning("Failed to load extension %s: %s", spec.name, exc)
        return extensions

    def load_from_entry_points(self, group: str = "agent_core.extensions") -> list[Extension]:
        extensions: list[Extension] = []
        try:
            eps = importlib.metadata.entry_points()
            if hasattr(eps, "select"):
                selected = eps.select(group=group)
            else:
                selected = eps.get(group, [])
            for ep in selected:
                try:
                    factory = ep.load()
                    if callable(factory):
                        ext = factory()
                        if ext is not None:
                            extensions.append(ext)
                except Exception as exc:
                    logger.warning("Failed to load extension entry point %s: %s", ep.name, exc)
        except Exception as exc:
            logger.warning("Failed to load entry points: %s", exc)
        return extensions

    def _load_spec(self, spec: ExtensionSpec) -> Extension | None:
        module = importlib.import_module(spec.module_path)
        # Look for Extension subclass or factory function
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and hasattr(attr, "name") and attr_name != "Extension":
                return attr()
        return None
