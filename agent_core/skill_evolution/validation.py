"""Skill Evolution Validation Gate.

This module implements the validation mechanism that ensures proposed skill
changes actually improve performance before being applied, inspired by EvoSkill.

The validation gate acts as a quality filter:
1. Takes a proposed skill change (patch)
2. Runs it against a test suite
3. Compares before/after performance
4. Only accepts changes with measurable improvement

This prevents "blind evolution" where changes might help one case but hurt others.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Callable

from .types import PatchProposal, TestCase, ValidationResult


_log = logging.getLogger(__name__)


class SkillValidationGate:
    """Validates proposed skill changes against test cases.

    This is the critical quality control component of the self-evolution system.
    Without validation, the system could degrade over time by accepting changes
    that help some cases but hurt others.

    Usage:
        gate = SkillValidationGate(skill_dir=".claude/skills")
        result = await gate.validate(proposal, test_cases)
        if result.passed:
            await gate.apply_proposal(proposal)
    """

    def __init__(
        self,
        skill_dir: str | Path = ".claude/skills",
        test_threshold: float = 0.05,  # Minimum improvement to accept
        timeout_per_test: float = 30.0,  # Seconds per test case
    ):
        """Initialize the validation gate.

        Args:
            skill_dir: Directory containing skill files
            test_threshold: Minimum score delta to accept change (default 5% improvement)
            timeout_per_test: Max seconds to run each test case
        """
        self.skill_dir = Path(skill_dir)
        self.test_threshold = test_threshold
        self.timeout_per_test = timeout_per_test

        # Test case registry - can be populated programmatically or from files
        self._test_cases: dict[str, list[TestCase]] = {}

    def register_test_cases(self, skill_name: str, cases: list[TestCase]) -> None:
        """Register test cases for a specific skill.

        Args:
            skill_name: Name of the skill these tests validate
            cases: List of test cases to register
        """
        self._test_cases[skill_name] = cases
        _log.info(f"[ValidationGate] Registered {len(cases)} test cases for {skill_name}")

    async def validate(
        self,
        proposal: PatchProposal,
        test_cases: list[TestCase] | None = None,
    ) -> ValidationResult:
        """Validate a proposed skill change.

        Args:
            proposal: The patch proposal to validate
            test_cases: Optional override list of test cases (uses registered if not provided)

        Returns:
            ValidationResult with pass/fail decision and detailed metrics
        """
        skill_name = proposal.skill_name
        cases = test_cases or self._test_cases.get(skill_name, [])

        if not cases:
            _log.warning(f"[ValidationGate] No test cases for {skill_name}, cannot validate")
            return ValidationResult(
                proposal_id=proposal.proposal_id,
                score_delta=0.0,
                passed=False,
                test_results=[],
                recommendation="needs_review",
            )

        _log.info(
            f"[ValidationGate] Validating proposal {proposal.proposal_id} "
            f"({proposal.operation} on {proposal.target_rule_id or 'new rule'})"
        )

        # Step 1: Load current skill content
        old_skill_content = await self._load_skill_content(skill_name)
        if not old_skill_content:
            _log.error(f"[ValidationGate] Could not load skill: {skill_name}")
            return ValidationResult(
                proposal_id=proposal.proposal_id,
                score_delta=0.0,
                passed=False,
                test_results=[],
                failed_cases=[tc.test_id for tc in cases],
                recommendation="reject",
            )

        # Step 2: Generate new skill content with proposal applied
        new_skill_content = self._apply_proposal(old_skill_content, proposal)

        # Step 3: Run tests on both versions
        old_scores = await self._run_tests(cases, old_skill_content, is_new=False)
        new_scores = await self._run_tests(cases, new_skill_content, is_new=True)

        # Step 4: Calculate aggregate score delta
        old_avg = sum(old_scores.values()) / len(old_scores) if old_scores else 0
        new_avg = sum(new_scores.values()) / len(new_scores) if new_scores else 0
        score_delta = new_avg - old_avg

        # Step 5: Determine pass/fail
        passed = score_delta >= self.test_threshold

        # Build detailed results
        test_results = []
        failed_cases = []
        for tc in cases:
            old_score = old_scores.get(tc.test_id, 0)
            new_score = new_scores.get(tc.test_id, 0)
            improved = new_score > old_score

            result_msg = f"{'✓' if improved else '✗'} {tc.test_id}: {old_score:.2f} → {new_score:.2f}"
            test_results.append((tc.test_id, improved, result_msg))

            if not improved:
                failed_cases.append(tc.test_id)

        # Generate recommendation
        if passed:
            recommendation = "accept"
        elif score_delta < -self.test_threshold:
            recommendation = "reject"
        else:
            recommendation = "needs_review"

        result = ValidationResult(
            proposal_id=proposal.proposal_id,
            score_delta=score_delta,
            passed=passed,
            test_results=test_results,
            failed_cases=failed_cases,
            recommendation=recommendation,
        )

        _log.info(
            f"[ValidationGate] Result: {result.recommendation} "
            f"(delta={score_delta:+.2f}, threshold={self.test_threshold})"
        )

        return result

    async def _load_skill_content(self, skill_name: str) -> str | None:
        """Load the current content of a skill file.

        Args:
            skill_name: Name of the skill (e.g., "dev-process-backend")

        Returns:
            Full content of SKILL.md or None if not found
        """
        skill_path = self.skill_dir / skill_name / "SKILL.md"
        if not skill_path.exists():
            return None

        return skill_path.read_text(encoding="utf-8")

    def _apply_proposal(
        self,
        old_content: str,
        proposal: PatchProposal,
    ) -> str:
        """Apply a patch proposal to skill content.

        Supported operations:
        - add: Insert new rule at end (before final ---)
        - modify: Replace existing rule content
        - delete: Remove a rule entirely
        - merge: Combine with existing rule (not yet implemented)
        """
        operation = proposal.operation
        target_rule = proposal.target_rule_id
        new_content = proposal.new_content

        if operation == "add":
            # Insert new rule before the final --- separator
            if "---\n\n##" in old_content:
                # Find last ## section and insert after it
                sections = old_content.split("---\n\n##")
                if len(sections) > 1:
                    # Add new rule as a new section
                    rule_number = self._extract_next_rule_number(old_content)
                    new_section = f"\n\n## 规则 {rule_number}：{new_content}\n\n"
                    return old_content.rstrip() + new_section + "---\n"
            else:
                # Simple append before final ---
                parts = old_content.rsplit("---", 1)
                if len(parts) == 2:
                    return parts[0] + f"\n\n## 新增规则：{new_content}\n\n---" + parts[1]

            # Fallback: just append
            return old_content + f"\n\n## 新增规则：{new_content}\n"

        elif operation == "modify" and target_rule:
            # Find and replace the target rule
            pattern = rf"(## 规则 \d+：.*?)(?=## 规则|\Z)"
            matches = list(re.finditer(pattern, old_content, re.DOTALL))

            for match in matches:
                rule_text = match.group(1)
                if target_rule in rule_text or self._rule_matches(rule_text, target_rule):
                    # Replace this rule
                    new_rule = f"## 规则 {target_rule.split('_')[1]}：{new_content}\n\n"
                    return old_content[:match.start()] + new_rule + old_content[match.end():]

            # If no match found, append as new rule
            return old_content + f"\n\n## 规则 {target_rule}：{new_content}\n"

        elif operation == "delete" and target_rule:
            # Remove the target rule
            pattern = rf"## 规则 \d+：.*?(?=## 规则|\Z)"
            return re.sub(pattern, "", old_content, count=1)

        else:
            _log.warning(f"[ValidationGate] Unknown operation: {operation}")
            return old_content

    def _extract_next_rule_number(self, content: str) -> int:
        """Extract the next available rule number from skill content."""
        matches = re.findall(r"## 规则 (\d+)：", content)
        if not matches:
            return 1
        return max(int(m) for m in matches) + 1

    def _rule_matches(self, rule_text: str, target_rule: str) -> bool:
        """Check if a rule block matches the target rule ID.

        Handles formats like:
        - "rule_14" → look for "规则 14"
        - "规则 14" → exact match
        """
        if target_rule.startswith("rule_"):
            num = target_rule.split("_")[1]
            return f"规则 {num}" in rule_text
        return target_rule in rule_text

    async def _run_tests(
        self,
        test_cases: list[TestCase],
        skill_content: str,
        is_new: bool = False,
    ) -> dict[str, float]:
        """Run test cases against a version of the skill.

        Args:
            test_cases: List of test cases to run
            skill_content: The skill content to test
            is_new: Whether this is the new (proposed) version

        Returns:
            Dict mapping test_id → score (0.0 to 1.0)
        """
        scores = {}

        # For now, use heuristic-based scoring since we don't have a real agent runner
        # In production, this would actually invoke the agent with the modified skill

        for tc in test_cases:
            try:
                # Simulate test execution with timeout
                score = await asyncio.wait_for(
                    self._execute_test_case(tc, skill_content),
                    timeout=self.timeout_per_test,
                )
                scores[tc.test_id] = score
            except asyncio.TimeoutError:
                _log.warning(f"[ValidationGate] Test {tc.test_id} timed out")
                scores[tc.test_id] = 0.0
            except Exception as e:
                _log.error(f"[ValidationGate] Test {tc.test_id} failed: {e}")
                scores[tc.test_id] = 0.0

        return scores

    async def _execute_test_case(
        self,
        test_case: TestCase,
        skill_content: str,
    ) -> float:
        """Execute a single test case and return a score.

        This is a simplified implementation. In production, this would:
        1. Create a temporary skill file with the test content
        2. Run the agent with the test query
        3. Check if expected behavior occurred
        4. Return a score based on success criteria

        For now, we use heuristic matching on the skill content itself.
        """
        # Heuristic scoring based on whether the skill content addresses the test
        query_lower = test_case.input_query.lower()
        skill_lower = skill_content.lower()

        # Check if relevant keywords from query appear in skill
        query_words = set(re.findall(r'\w+', query_lower))
        skill_words = set(re.findall(r'\w+', skill_lower))

        overlap = len(query_words & skill_words) / len(query_words) if query_words else 0

        # Base score on keyword overlap
        base_score = min(overlap * 2, 1.0)  # Scale up but cap at 1.0

        # Bonus if expected behavior keywords are present
        expected_lower = test_case.expected_behavior.lower()
        expected_words = set(re.findall(r'\w+', expected_lower))
        expected_overlap = len(expected_words & skill_words) / len(expected_words) if expected_words else 0
        bonus = expected_overlap * 0.2

        return min(base_score + bonus, 1.0)

    async def apply_proposal(
        self,
        proposal: PatchProposal,
        backup: bool = True,
    ) -> bool:
        """Apply an accepted proposal to the actual skill file.

        Args:
            proposal: The validated proposal to apply
            backup: Whether to create a backup before modifying

        Returns:
            True if successfully applied
        """
        skill_path = self.skill_dir / proposal.skill_name / "SKILL.md"

        if not skill_path.exists():
            _log.error(f"[ValidationGate] Skill file not found: {skill_path}")
            return False

        # Create backup if requested
        if backup:
            backup_path = skill_path.with_suffix(".md.bak")
            backup_path.write_text(skill_path.read_text(encoding="utf-8"), encoding="utf-8")
            _log.info(f"[ValidationGate] Created backup: {backup_path}")

        # Read current content
        old_content = skill_path.read_text(encoding="utf-8")

        # Apply proposal
        new_content = self._apply_proposal(old_content, proposal)

        # Write back
        skill_path.write_text(new_content, encoding="utf-8")
        _log.info(f"[ValidationGate] Applied proposal {proposal.proposal_id} to {proposal.skill_name}")

        return True


def create_validation_gate(
    skill_dir: str | Path = ".claude/skills",
    test_threshold: float = 0.05,
) -> SkillValidationGate:
    """Factory function to create a validation gate.

    Args:
        skill_dir: Directory containing skill files
        test_threshold: Minimum improvement to accept changes

    Returns:
        Configured SkillValidationGate
    """
    return SkillValidationGate(skill_dir, test_threshold=test_threshold)
