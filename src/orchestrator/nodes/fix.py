"""Fix Node - Call Opus 4.6, apply code edits."""

from __future__ import annotations

import re
from pathlib import Path

from src.brain.client import call_opus
from src.brain.prompts import FIX_SYSTEM_PROMPT, FIX_USER_PROMPT_TEMPLATE
from src.orchestrator.state import PhoenixState


def _resolve_file_path(
    repo_path: str, file_path: str, stack_trace: str, error_summary: str = ""
) -> Path | None:
    """Resolve full file path. Uses file_path, else parses stack_trace, else searches repo."""
    repo = Path(repo_path)
    if not repo.exists():
        return None

    # 1. Direct path from state (Sentry or manual)
    if file_path:
        path_clean = file_path.lstrip("/").split("?")[0]
        candidate = repo / path_clean
        if candidate.exists():
            return candidate
        # Search repo for filename (works for any project structure)
        fname = Path(path_clean).name
        for p in repo.rglob(fname):
            if "node_modules" not in str(p) and "dist" not in str(p):
                return p

    # 2. Parse filename from stack trace and search repo (no fixed paths)
    match = re.search(r"[\w/.-]+\.(?:ts|tsx|js|jsx|py|java)(?=:\d|\)|$)", stack_trace or "")
    if match:
        fname = Path(match.group(0).strip()).name
        for p in repo.rglob(fname):
            if "node_modules" not in str(p) and "dist" not in str(p):
                return p

    # 3. Generic: extract class/method from culprit/stack, search repo by content
    # No hardcoded filenames — works for any repo
    culprit_stack = f"{stack_trace or ''} {file_path or ''}".strip()
    # Culprit pattern: "Service.method" or "JSON.parse"
    culprit_match = re.search(r"([A-Za-z_][\w.]*(?:\.[A-Za-z_][\w.]*)+)", culprit_stack)
    if culprit_match:
        culprit_part = culprit_match.group(1)
        tokens = re.findall(r"[A-Za-z_][a-zA-Z0-9]*", culprit_part)
    else:
        tokens = re.findall(r"[A-Z][a-z0-9]+|[a-z][a-zA-Z0-9]*", culprit_stack)
    skip = (
        "the", "and", "for", "main", "anonymous", "null", "undefined",
        "error", "syntax", "expected", "property", "name", "position", "line", "column", "at",
    )
    tokens = [t for t in tokens if len(t) > 2 and t.lower() not in skip]

    ext = ("*.ts", "*.tsx", "*.js", "*.jsx", "*.py")
    candidates: list[tuple[int, Path, str]] = []  # (matches, path, content)
    for ext_pattern in ext:
        for p in repo.rglob(ext_pattern):
            if "node_modules" in str(p) or "dist" in str(p):
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                matches = sum(1 for t in tokens if t in content)
                if matches > 0:
                    candidates.append((matches, p, content))
            except Exception:
                pass

    if candidates:
        def score(item: tuple[int, Path, str]) -> tuple:
            matches, p, content = item
            s = str(p)
            name = p.stem.lower()
            name_bonus = sum(1 for t in tokens if t.lower() in name or name in t.lower())
            path_prefer = 1 if any(x in s for x in ("src", "lib", "app")) else 0
            # CRITICAL: Prefer files that EXECUTE the code, not data files that mention it
            # JSON.parse culprit -> prefer file with actual JSON.parse( call
            source_bonus = 0
            tok_lower = {t.lower() for t in tokens}
            if "json" in tok_lower and "parse" in tok_lower and "JSON.parse(" in content:
                source_bonus = 10  # Actual call site, not just string mention
            # Penalize data/config files (often metadata, not execution)
            if ".data." in name or "/data/" in s:
                source_bonus -= 5
            return (source_bonus, matches, name_bonus, path_prefer)

        best = max(candidates, key=score)
        return best[1]

    return None


def _extract_code_from_response(response: str) -> str | None:
    """Extract code from markdown code block in AI response (any language)."""
    match = re.search(r"```(?:\w+)?\s*\n(.*?)\n```", response, re.DOTALL)
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
    target_file = _resolve_file_path(repo_path, file_path, stack_trace, error_summary)
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
