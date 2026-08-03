#!/usr/bin/env python3
"""CLI: verify skill evolution end-to-end closed loop.

Examples:

    # CI-safe (mock agent_runner, temp dirs, no network)
    python scripts/verify_skill_evolution_e2e.py

    # Keep temp workdir for inspection
    SKILL_EVOLUTION_E2E_KEEP_WORKDIR=1 python scripts/verify_skill_evolution_e2e.py

    # Optional: real LLM agent_runner (needs API keys)
    python scripts/verify_skill_evolution_e2e.py --live

    # Via pytest
    pytest tests/skill_evolution/test_e2e_verify.py -v
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running from repo root without install
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent_core.skill_evolution.e2e_verify import run_skill_evolution_e2e


def main() -> int:
    parser = argparse.ArgumentParser(description="Skill evolution E2E verification")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use real ValidationHarnessRunner (requires LLM API keys)",
    )
    parser.add_argument(
        "--jsonl",
        action="store_true",
        help="Use JsonlSkillEvolutionStore instead of in-memory",
    )
    parser.add_argument(
        "--skill-name",
        default="e2e-test-skill",
        help="Skill name for the fixture (default: e2e-test-skill)",
    )
    parser.add_argument(
        "--min-traces",
        type=int,
        default=10,
        help="Minimum traces before analyze (default: 10)",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=None,
        help="Optional fixed work directory (not auto-deleted unless keep flag set)",
    )
    args = parser.parse_args()

    result = asyncio.run(
        run_skill_evolution_e2e(
            skill_name=args.skill_name,
            min_traces=args.min_traces,
            use_live_runner=args.live,
            workdir=args.workdir,
            use_jsonl_store=args.jsonl,
        )
    )
    print(result.summary())
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
