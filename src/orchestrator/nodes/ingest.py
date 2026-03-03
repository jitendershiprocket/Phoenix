"""Ingest & Analyze Node - Parse error, identify repo/file, fetch metadata."""

import os

from src.orchestrator.state import PhoenixState


def ingest_node(state: PhoenixState) -> dict:
    """Parse error payload and extract context for the fix node.
    Uses Repo Analyzer to fetch angular/node versions when not in payload.
    """
    payload = state.get("error_payload", {})
    repo_url = state.get("repo_url", "")
    branch = state.get("branch", "main")

    angular_version = payload.get("angular_version")
    node_version = payload.get("node_version")

    # If metadata missing, use Repo Analyzer (requires GITHUB_TOKEN)
    if (not angular_version or not node_version) and repo_url and os.getenv("GITHUB_TOKEN"):
        try:
            from src.analyzer.repo_analyzer import RepoAnalyzer
            analyzer = RepoAnalyzer()
            diag = analyzer.analyze(repo_url, branch)
            angular_version = angular_version or diag.angular_version
            node_version = node_version or diag.node_version
        except Exception:
            pass

    return {
        "error_summary": payload.get("error_summary", state.get("error_summary", "")),
        "file_path": payload.get("file_path", state.get("file_path", "")),
        "stack_trace": payload.get("stack_trace", state.get("stack_trace", "")),
        "line_number": payload.get("line_number") if payload.get("line_number") is not None else state.get("line_number"),
        "culprit": payload.get("culprit", state.get("culprit", "")),
        "angular_version": angular_version,
        "node_version": node_version,
    }
