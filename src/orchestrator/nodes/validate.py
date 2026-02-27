"""Validate Node - Run ng test and ng lint."""

from src.orchestrator.state import PhoenixState
from src.services.validator import run_ng_lint, run_ng_test


def validate_node(state: PhoenixState) -> dict:
    """Run ng test and ng lint in repo_path. Return pass/fail."""
    repo_path = state.get("repo_path", "")
    if not repo_path:
        return {
            "tests_passed": False,
            "lint_passed": False,
            "validation_log": "No repo_path",
        }

    tests_passed, test_log = run_ng_test(repo_path)
    lint_passed, lint_log = run_ng_lint(repo_path)
    validation_log = f"--- ng test ---\n{test_log}\n--- ng lint ---\n{lint_log}"
    return {
        "tests_passed": tests_passed,
        "lint_passed": lint_passed,
        "validation_log": validation_log,
    }
