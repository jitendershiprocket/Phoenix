"""Validate Node - Run ng build and ng lint (no unit tests; build catches TS/type errors)."""

from src.orchestrator.state import PhoenixState
from src.services.validator import run_ng_build, run_ng_lint


def validate_node(state: PhoenixState) -> dict:
    """Run ng build and ng lint in repo_path. Return pass/fail."""
    repo_path = state.get("repo_path", "")
    if not repo_path:
        return {
            "tests_passed": False,
            "lint_passed": False,
            "validation_log": "No repo_path",
        }

    build_passed, build_log = run_ng_build(repo_path)
    lint_passed, lint_log = run_ng_lint(repo_path)
    validation_log = f"--- ng build ---\n{build_log}\n--- ng lint ---\n{lint_log}"
    return {
        "tests_passed": build_passed,  # build = TS/type safety check
        "lint_passed": lint_passed,
        "validation_log": validation_log,
    }
