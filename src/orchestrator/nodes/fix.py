"""Fix Node - Call Opus 4.6, apply code edits."""

from __future__ import annotations

import re
from pathlib import Path

from src.brain.client import call_opus
from src.brain.prompts import FIX_SYSTEM_PROMPT, FIX_USER_PROMPT_TEMPLATE
from src.orchestrator.state import PhoenixState


def _resolve_file_path(repo_path: str, file_path: str, stack_trace: str) -> Path | None:
    """Resolve full file path. Uses file_path, else parses stack_trace, else searches repo."""
    repo = Path(repo_path)
    if not repo.exists():
        return None

    # 1. Direct path from state
    if file_path:
        candidate = repo / file_path.lstrip("/")
        if candidate.exists():
            return candidate
        # Try src/ prefix (Angular structure)
        for prefix in ("src/", "src/app/"):
            candidate = repo / prefix / file_path.lstrip("/")
            if candidate.exists():
                return candidate

    # 2. Parse from stack trace: "user.service.ts:27" or "src/app/services/user.service.ts:27"
    match = re.search(r"[\w/.-]+\.(?:ts|tsx|js)(?=:\d|\)|$)", stack_trace or "")
    if match:
        rel = match.group(0).strip()
        for p in [repo / rel, repo / "src" / rel, repo / "src/app" / rel]:
            if p.exists():
                return p

    # 3. Heuristic: UserService -> user.service.ts
    if "UserService" in (stack_trace or ""):
        for p in repo.rglob("user.service.ts"):
            return p

    return None


def _extract_code_from_response(response: str) -> str | None:
    """Extract code from markdown code block in AI response."""
    match = re.search(r"```(?:typescript|ts|javascript|js)?\s*\n(.*?)\n```", response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def fix_node(state: PhoenixState) -> dict:
    """Use Opus 4.6 to generate fix and apply to repo."""
    repo_path = state.get("repo_path", "")
    error_summary = state.get("error_summary", "")
    stack_trace = state.get("stack_trace", error_summary)
    file_path = state.get("file_path", "")

    fix_attempt = state.get("fix_attempt", 0) + 1
    max_attempts = state.get("max_attempts", 3)

    if not repo_path or not error_summary:
        return {
            "fix_attempt": fix_attempt,
            "fix_applied": False,
        }

    # Resolve file to fix
    target_file = _resolve_file_path(repo_path, file_path, stack_trace)
    if not target_file:
        return {
            "fix_attempt": fix_attempt,
            "fix_applied": False,
            "validation_log": f"Could not resolve file from stack_trace. file_path={file_path!r}",
        }

    try:
        file_content = target_file.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {
            "fix_attempt": fix_attempt,
            "fix_applied": False,
            "validation_log": str(e),
        }

    # Call Opus 4.6
    user_prompt = FIX_USER_PROMPT_TEMPLATE.format(
        error_summary=error_summary,
        stack_trace=stack_trace,
        file_path=str(target_file.relative_to(Path(repo_path))) if repo_path else str(target_file),
        file_content=file_content,
    )

    try:
        response = call_opus(FIX_SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        return {
            "fix_attempt": fix_attempt,
            "fix_applied": False,
            "validation_log": f"AI call failed: {e}",
        }

    fixed_code = _extract_code_from_response(response)
    if not fixed_code:
        return {
            "fix_attempt": fix_attempt,
            "fix_applied": False,
            "validation_log": "AI did not return valid code block",
        }

    try:
        target_file.write_text(fixed_code, encoding="utf-8")
    except Exception as e:
        return {
            "fix_attempt": fix_attempt,
            "fix_applied": False,
            "validation_log": str(e),
        }

    rel_path = str(target_file.relative_to(Path(repo_path))) if repo_path else str(target_file)
    return {
        "fix_attempt": fix_attempt,
        "fix_applied": True,
        "file_path": rel_path,
    }
