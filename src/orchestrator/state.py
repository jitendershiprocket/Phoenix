"""Phoenix Agent - Shared State Schema for LangGraph."""

from typing import Optional, TypedDict


class PhoenixState(TypedDict, total=False):
    """Shared state passed between LangGraph nodes."""

    # === Input ===
    error_payload: dict
    repo_url: str
    branch: str
    search_scope: Optional[list]  # e.g. ["src/app"] to limit file scan for large repos
    local_repo_path: Optional[str]  # if set, use this path instead of cloning (for dev/testing)
    upstream_url: Optional[str]  # if set (fork workflow), pull from here, PR base repo

    # === After Ingest ===
    error_summary: str
    file_path: str
    stack_trace: str
    line_number: Optional[int]
    culprit: str
    angular_version: Optional[str]
    node_version: Optional[str]

    # === After Clone ===
    repo_path: str
    fix_branch: str

    # === After Fix ===
    fix_applied: bool
    fix_attempt: int
    max_attempts: int
    fix_failure_reason: str  # when fix_applied=False

    # === After Validate ===
    tests_passed: bool
    lint_passed: bool
    validation_log: str

    # === After PR ===
    pr_url: Optional[str]
    status: str  # "success" | "failed" | "aborted"
