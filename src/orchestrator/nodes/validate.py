"""Validate Node - Run ng build and ng lint (no unit tests; build catches TS/type errors)."""

from pathlib import Path

from src.orchestrator.state import PhoenixState
from src.services.validator import run_ng_build, run_ng_lint, run_lint_changed_only


def _get_lint_changed_only() -> bool:
    try:
        config_path = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
        if config_path.exists():
            import yaml
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
            return cfg.get("validation", {}).get("lint_changed_only", True)
    except Exception:
        pass
    return True


def validate_node(state: PhoenixState) -> dict:
    """Run ng build and ng lint in repo_path. Lint only changed file if configured."""
    repo_path = state.get("repo_path", "")
    if not repo_path:
        return {
            "tests_passed": False,
            "lint_passed": False,
            "validation_log": "No repo_path",
        }

    build_passed, build_log = run_ng_build(repo_path)
    file_path = state.get("file_path", "")
    lint_changed_only = _get_lint_changed_only()

    if lint_changed_only and file_path:
        lint_passed, lint_log = run_lint_changed_only(repo_path, file_path)
        lint_label = f"--- eslint (changed: {file_path}) ---"
    else:
        lint_passed, lint_log = run_ng_lint(repo_path)
        lint_label = "--- ng lint ---"

    validation_log = f"--- ng build ---\n{build_log}\n{lint_label}\n{lint_log}"
    return {
        "tests_passed": build_passed,
        "lint_passed": lint_passed,
        "validation_log": validation_log,
    }
