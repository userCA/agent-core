#!/usr/bin/env python3
"""Rename dirty evolution jsonl so new runs start clean. Never deletes."""

from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    base = Path(os.path.expanduser("~/.agent-core"))
    src = base / "skill-evolution-traces.jsonl"
    dst = base / "skill-evolution-traces.jsonl.legacy-20260731"
    if not src.exists():
        print("skip: no source file", src)
        return
    if dst.exists():
        print("skip: legacy already exists", dst)
        return
    src.rename(dst)
    print(f"moved {src} -> {dst}")


if __name__ == "__main__":
    main()
