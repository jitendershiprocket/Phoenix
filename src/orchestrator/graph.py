"""Phoenix Agent - LangGraph Orchestrator.

Flow: INGEST → CLONE → FIX → VALIDATE → (PR | back to FIX on fail)
"""

import time

from langgraph.graph import StateGraph, END
from .state import PhoenixState
from .nodes import ingest_node, clone_node, fix_node, validate_node, pr_node, abort_node


def _wrap_with_progress(node_fn, step_name: str):
    """Wrap node to report progress to dashboard."""
    try:
        from src.dashboard.progress import progress
    except ImportError:
        return node_fn

    def wrapped(state):
        msg = ""
        if step_name == "fix":
            msg = "AI generating fix..."
        elif step_name == "validate":
            msg = "ng build running..."
        progress.step_start(step_name, msg)
        t0 = time.time()
        try:
            out = node_fn(state)
            success = True
            if step_name == "clone" and not out.get("repo_path"):
                success = False
            elif step_name == "fix" and out.get("fix_failure_reason"):
                success = False
            elif step_name == "validate":
                success = bool(out.get("tests_passed") and out.get("lint_passed"))
            elif step_name == "pr" and out.get("status") == "failed":
                success = False
            msg = out.get("validation_log", "")[:150] or out.get("fix_failure_reason", "")[:150] or ("Done" if success else "Failed")
            progress.step_end(step_name, time.time() - t0, msg, success)
            if step_name == "pr" and out.get("pr_url"):
                progress.set_pr_url(out["pr_url"])
            return out
        except Exception as e:
            progress.step_end(step_name, time.time() - t0, str(e)[:150], False)
            raise

    return wrapped


def build_phoenix_graph(enable_dashboard: bool = True):
    """Build the LangGraph state machine for Project Phoenix."""
    graph = StateGraph(PhoenixState)

    clone = _wrap_with_progress(clone_node, "clone") if enable_dashboard else clone_node
    fix = _wrap_with_progress(fix_node, "fix") if enable_dashboard else fix_node
    validate = _wrap_with_progress(validate_node, "validate") if enable_dashboard else validate_node
    pr = _wrap_with_progress(pr_node, "pr") if enable_dashboard else pr_node

    graph.add_node("ingest", ingest_node)
    graph.add_node("clone", clone)
    graph.add_node("fix", fix)
    graph.add_node("validate", validate)
    graph.add_node("pr", pr)
    graph.add_node("abort", abort_node)

    # Define flow
    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "clone")
    graph.add_conditional_edges("clone", _after_clone, {"fix": "fix", "abort": "abort"})
    graph.add_edge("fix", "validate")

    # Conditional: validate pass → PR, fail → fix (retry) or END
    graph.add_conditional_edges(
        "validate",
        _should_create_pr,
        {
            "pr": "pr",
            "retry_fix": "fix",
            "abort": "abort",
        },
    )
    graph.add_edge("abort", END)
    graph.add_edge("pr", END)

    return graph.compile()


def _after_clone(state: PhoenixState) -> str:
    """If clone failed (no repo_path), abort early with the actual error."""
    repo_path = state.get("repo_path", "")
    if not repo_path:
        return "abort"
    return "fix"


def _should_create_pr(state: PhoenixState) -> str:
    """Route after validation: pr, retry_fix, or abort."""
    tests_passed = state.get("tests_passed", False)
    lint_passed = state.get("lint_passed", False)
    fix_attempt = state.get("fix_attempt", 0)
    max_attempts = state.get("max_attempts", 3)

    if tests_passed and lint_passed:
        return "pr"
    if fix_attempt < max_attempts:
        return "retry_fix"
    return "abort"
