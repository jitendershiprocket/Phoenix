"""Phoenix Agent - LangGraph Orchestrator.

Flow: INGEST → CLONE → FIX → VALIDATE → (PR | back to FIX on fail)
"""

from langgraph.graph import StateGraph, END
from .state import PhoenixState
from .nodes import ingest_node, clone_node, fix_node, validate_node, pr_node, abort_node


def build_phoenix_graph():
    """Build the LangGraph state machine for Project Phoenix."""
    graph = StateGraph(PhoenixState)

    # Add nodes
    graph.add_node("ingest", ingest_node)
    graph.add_node("clone", clone_node)
    graph.add_node("fix", fix_node)
    graph.add_node("validate", validate_node)
    graph.add_node("pr", pr_node)
    graph.add_node("abort", abort_node)

    # Define flow
    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "clone")
    graph.add_edge("clone", "fix")
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
