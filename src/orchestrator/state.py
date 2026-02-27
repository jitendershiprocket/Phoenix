"""Phoenix Agent - Shared State Schema for LangGraph."""

from typing import Optional, TypedDict


class PhoenixState(TypedDict, total=False):
    """Shared state passed between LangGraph nodes."""

    # === Input ===
    error_payload: dict
    repo_url: str
    branch: str

    # === After Ingest ===
    error_summary: str
    file_path: str
    stack_trace: str
    angular_version: Optional[str]
    node_version: Optional[str]

    # === After Clone ===
    repo_path: str
    fix_branch: str

    # === After Fix ===
    fix_applied: bool
    fix_attempt: int
    max_attempts: int

    # === After Validate ===
    tests_passed: bool
    lint_passed: bool
    validation_log: str

    # === After PR ===
    pr_url: Optional[str]
    status: str  # "success" | "failed" | "aborted"
