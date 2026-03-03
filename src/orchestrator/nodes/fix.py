"""Fix Node - Call Opus 4.6, apply code edits."""

from __future__ import annotations

import re
from pathlib import Path

from src.brain.client import call_opus
from src.brain.prompts import FIX_SYSTEM_PROMPT, FIX_USER_PROMPT_TEMPLATE
from src.orchestrator.state import PhoenixState


def _extract_error_property(error_summary: str) -> str | None:
    """Extract property name from 'reading X' or 'reading \"X\"' in error message."""
    m = re.search(r"reading\s+['\"](\w+)['\"]", error_summary or "", re.I)
    return m.group(1) if m else None


def _path_priority_score(path_str: str) -> int:
    """Higher = more likely source. Generic — no assumptions about folder structure.

    Architecture varies: helpers may be in lib/, utils/, or scattered. We only prefer
    paths that look like source (src, app, lib) over test/temp. No folder-to-type mapping.
    """
    s = path_str.lower()
    # Generic: has common source indicators (Angular/React/Vue often use these)
    if "/src/" in s or "\\src\\" in s:
        return 50
    if "/app/" in s or "\\app\\" in s:
        return 45
    if "/lib/" in s or "\\lib\\" in s:
        return 40
    # Anything outside node_modules/dist (already excluded) gets base score
    return 20


def _resolve_file_path(
    repo_path: str, file_path: str, stack_trace: str, error_summary: str = "",
    search_scope: list | None = None,
) -> Path | None:
    """Resolve full file path. Works for ANY file — service, component, util, pipe, etc.

    Uses: (1) direct path, (2) filename from stack, (3) content search by culprit tokens.
    search_scope limits scan (e.g. ["src/app"]) for large codebases.
    """
    repo = Path(repo_path)
    if not repo.exists():
        return None

    def _rglob_filtered(pattern: str) -> list[Path]:
        if search_scope:
            out = []
            for scope in search_scope:
                sp = repo / scope.strip("/")
                if sp.exists():
                    out.extend(p for p in sp.rglob(pattern)
                               if "node_modules" not in str(p) and "dist" not in str(p))
            if out:
                return out
        return [p for p in repo.rglob(pattern)
                if "node_modules" not in str(p) and "dist" not in str(p)]

    # 1. Direct path from state (Sentry or manual). Skip Sentry's ":?" (unknown)
    if file_path and file_path.strip() not in (":", ":?", "?"):
        path_clean = file_path.lstrip("/").split("?")[0]
        candidate = repo / path_clean
        if candidate.exists():
            return candidate
        fname = Path(path_clean).name
        same_name = _rglob_filtered(fname)
        if same_name:
            return max(same_name, key=lambda p: _path_priority_score(str(p)))

    # 2. Parse filename from stack trace and search repo (no fixed paths)
    match = re.search(r"[\w/.-]+\.(?:ts|tsx|js|jsx|py|java)(?=:\d|\)|$)", stack_trace or "")
    if match:
        fname = Path(match.group(0).strip()).name
        same_name = _rglob_filtered(fname)
        if same_name:
            return max(same_name, key=lambda p: _path_priority_score(str(p)))

    # 2b. Culprit "SettingsComponent.loadSettingData" -> search settings.component.ts directly
    culprit_match = re.search(r"([A-Za-z_][\w.]*(?:\.[A-Za-z_][\w.]*)+)", (stack_trace or "") + " " + (file_path or ""))
    if culprit_match:
        parts = re.findall(r"[A-Z][a-z]*|[a-z]+", culprit_match.group(1).split(".")[0])
        if parts and (parts[-1] in ("Component", "Service", "Module", "Pipe", "Directive")):
            base = "".join(p.lower() for p in parts[:-1])
            suffix = parts[-1].lower()
            for fname_pattern in (f"{base}.{suffix}.ts", f"{base}.{suffix}.tsx", f"{base}-{suffix}.ts"):
                same = _rglob_filtered(fname_pattern)
                if same:
                    return max(same, key=lambda p: _path_priority_score(str(p)))

    # 3. Generic: extract identifiers from culprit/stack — works for ANY file type
    # (services, components, utils, helpers, pipes, guards, standalone functions, etc.)
    culprit_stack = f"{stack_trace or ''} {file_path or ''}".strip()
    # Class.method, Module.fn, or standalone fn (formatDate, parseJSON, etc.)
    culprit_match = re.search(r"([A-Za-z_][\w.]*(?:\.[A-Za-z_][\w.]*)+)", culprit_stack)
    if culprit_match:
        culprit_part = culprit_match.group(1)
        tokens = re.findall(r"[A-Za-z_][a-zA-Z0-9]*", culprit_part)
    else:
        # Standalone fn/class: formatDate, UserUtils, parseJSON
        tokens = re.findall(r"[A-Za-z_][a-zA-Z0-9]{2,}", culprit_stack)
    # Add normalized tokens: _CacheService -> CacheService (minified)
    extra = [t[1:] for t in tokens if t.startswith("_") and len(t) > 1]
    tokens = list(dict.fromkeys(tokens + extra))
    skip = (
        "the", "and", "for", "main", "anonymous", "null", "undefined",
        "error", "syntax", "expected", "property", "name", "position", "line", "column", "at",
    )
    tokens = [t for t in tokens if len(t) > 2 and t.lower() not in skip]

    # Path hint from culprit: SettingsComponent → prefer paths with "settings"
    path_hints: list[str] = []
    for t in tokens:
        if t.endswith("Component") or t.endswith("Service") or t.endswith("Module"):
            base = re.sub(r"(Component|Service|Module)$", "", t, flags=re.I)
            if base and len(base) > 2:
                parts = re.findall(r"[a-z]+|[A-Z][a-z]*", base)
                path_hints = [p.lower() for p in parts if len(p) > 1]
                break

    ext = ("*.ts", "*.tsx", "*.js", "*.jsx", "*.py")
    candidates: list[tuple[int, Path, str]] = []  # (matches, path, content)
    max_files = 120  # cap content reads for large repos
    seen = 0
    for ext_pattern in ext:
        if len(candidates) >= 10 and any(c[0] >= 3 for c in candidates):
            break  # early exit if we have good matches
        for p in _rglob_filtered(ext_pattern):
            if seen >= max_files:
                break
            if path_hints:
                pstr = str(p).lower()
                if not any(h in pstr for h in path_hints):
                    continue
            seen += 1
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                matches = sum(1 for t in tokens if t in content)
                if matches > 0:
                    candidates.append((matches, p, content))
            except Exception:
                pass
        if seen >= max_files:
            break

    if candidates:
        error_prop = _extract_error_property(error_summary)

        def score(item: tuple[int, Path, str]) -> tuple:
            matches, p, content = item
            s = str(p)
            name = p.stem.lower()
            # Token overlaps filename: FormatUtils <-> format-utils, UserService <-> user.service
            def token_matches_name(tok: str, fname: str) -> bool:
                tl, fn = tok.lower(), fname.lower()
                if tl in fn or fn in tl:
                    return True
                # CamelCase -> kebab/dot: FormatUtils vs format-utils
                parts = re.findall(r"[a-z]+|[A-Z][a-z]*", tok)
                if len(parts) > 1 and all(p.lower() in fn for p in parts):
                    return True
                return False
            name_bonus = sum(1 for t in tokens if token_matches_name(t, name))
            # Generic: XxxSuffix -> xxx.suffix.ts or xxx-suffix.ts (any file type)
            # Works for Service, Component, Pipe, Directive, Guard, Util, Helper, etc.
            type_bonus = 0
            suffixes = [
                ("Service", 7), ("Component", 9), ("Pipe", 4), ("Directive", 9),
                ("Guard", 5), ("Interceptor", 11), ("Util", 4), ("Utils", 5),
                ("Helper", 6), ("Helpers", 7), ("Factory", 7), ("Provider", 8),
            ]
            for t in tokens:
                for suffix, ln in suffixes:
                    if t.endswith(suffix) and len(t) > ln:
                        base = t[:-ln].lower()
                        # Match: user.service, format-utils, date-helper, etc.
                        if base in name or name.startswith(base + ".") or name.startswith(base + "-"):
                            type_bonus = 10
                            break
                if type_bonus:
                    break
            path_priority = _path_priority_score(s)
            # CRITICAL: Prefer definition site over call site. CacheService.get = file that DEFINES get()
            # (has "class CacheService" + "get("), not file that just calls cacheService.get()
            definition_bonus = 0
            if culprit_match:
                # tokens like ["CacheService", "get"] — look for class def + method
                class_tok = next((t for t in tokens if t[0].isupper() and not t.startswith("_")), None)
                method_tok = next((t for t in tokens if t[0].islower() and len(t) > 2), None)
                if class_tok and method_tok:
                    class_pat = rf"(?:export\s+)?(?:class|function)\s+{re.escape(class_tok)}\b"
                    method_pat = rf"\b{re.escape(method_tok)}\s*\("
                    if re.search(class_pat, content) and re.search(method_pat, content):
                        definition_bonus = 15  # Strong: this file defines the failing method
            # JSON.parse culprit -> prefer file with actual JSON.parse( call
            source_bonus = 0
            tok_lower = {t.lower() for t in tokens}
            if "json" in tok_lower and "parse" in tok_lower and "JSON.parse(" in content:
                source_bonus = 10
            # Error "reading 'value'" -> prefer file with .value (including (expr).value)
            error_pattern_bonus = 0
            if error_prop and re.search(rf"\.{re.escape(error_prop)}\b", content):
                error_pattern_bonus = 5  # Has property access; def_bonus is stronger signal
            # Penalize data/config files (often metadata, not execution)
            if ".data." in name or "/data/" in s:
                source_bonus -= 5
            return (
                definition_bonus, type_bonus, source_bonus, error_pattern_bonus,
                matches, name_bonus, path_priority,
            )

        best = max(candidates, key=score)
        return best[1]

    return None


def _extract_code_from_response(response: str) -> str | None:
    """Extract code from markdown code block in AI response (any language)."""
    match = re.search(r"```(?:\w+)?\s*\n(.*?)\n```", response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def _apply_optional_chaining_fix(content: str, error_prop: str) -> str | None:
    """Rule-based fix for 'Cannot read properties of undefined (reading X)'.
    Generic: finds any chain.property (or chain().property) without ?. and adds optional chaining.
    Returns modified content if changed, else None."""
    if not error_prop:
        return None

    # Regex: match chain.property — chain can be ident, ident.ident, ident(), ident().prop, etc.
    pattern = rf"\b([a-zA-Z_$][\w$]*(?:\(\))?(?:\.[a-zA-Z_$][\w$]*(?:\(\))?)*)\.({re.escape(error_prop)})\b"
    modified = False

    def replacer(m: re.Match) -> str:
        nonlocal modified
        chain = m.group(1)
        prop = m.group(2)
        if "?." in chain:
            return m.group(0)
        modified = True
        return chain.replace(".", "?.") + "?." + prop

    result = re.sub(pattern, replacer, content)
    return result if modified else None


def _find_files_with_property(
    repo_path: str | Path, error_prop: str, search_scope: list | None, exclude_path: Path | None
) -> list[Path]:
    """Find files that contain .error_prop (potential bug site) for multi-file rule-based fix."""
    repo = Path(repo_path)
    if not repo.exists():
        return []

    def _rglob_filtered(pattern: str) -> list[Path]:
        if search_scope:
            out = []
            for scope in search_scope:
                sp = repo / scope.strip("/")
                if sp.exists():
                    out.extend(p for p in sp.rglob(pattern)
                               if "node_modules" not in str(p) and "dist" not in str(p))
            return out
        return [p for p in repo.rglob(pattern)
                if "node_modules" not in str(p) and "dist" not in str(p)]

    candidates: list[Path] = []
    for ext in ("*.ts", "*.tsx", "*.js", "*.jsx"):
        for p in _rglob_filtered(ext):
            if exclude_path and p.resolve() == exclude_path.resolve():
                continue
            try:
                if f".{error_prop}" in p.read_text(encoding="utf-8", errors="ignore"):
                    candidates.append(p)
            except Exception:
                pass
    return candidates


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
            "fix_failure_reason": "Missing repo_path or error_summary",
        }

    # Resolve file to fix (search_scope limits scan for large repos)
    search_scope = state.get("search_scope")
    target_file = _resolve_file_path(
        repo_path, file_path, stack_trace, error_summary, search_scope=search_scope
    )
    if not target_file:
        return {
            "fix_attempt": fix_attempt,
            "fix_applied": False,
            "fix_failure_reason": f"Could not resolve file. file_path={file_path!r}, culprit=loadSettingData",
            "validation_log": f"Could not resolve file from stack_trace. file_path={file_path!r}",
        }

    try:
        file_content = target_file.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {
            "fix_attempt": fix_attempt,
            "fix_applied": False,
            "fix_failure_reason": f"Could not read file: {e}",
            "validation_log": str(e),
        }

    # Rule-based fix for "Cannot read properties of undefined (reading 'X')" — add optional chaining
    is_undefined_prop_error = "Cannot read properties of undefined" in (error_summary or "") and "reading" in (error_summary or "")
    error_prop = _extract_error_property(error_summary)
    if is_undefined_prop_error and error_prop:
        fixed_content = _apply_optional_chaining_fix(file_content, error_prop)
        if fixed_content and fixed_content != file_content:
            try:
                target_file.write_text(fixed_content, encoding="utf-8")
                rel_path = str(target_file.relative_to(Path(repo_path))) if repo_path else str(target_file)
                return {
                    "fix_attempt": fix_attempt,
                    "fix_applied": True,
                    "file_path": rel_path,
                }
            except Exception as e:
                pass  # fall through to AI

    # Call Opus 4.6
    line_number = state.get("line_number")
    culprit = state.get("culprit", "") or ""
    # Extract failing function from culprit: "_SettingsComponent.loadSettingData(...)" -> "loadSettingData"
    failing_fn = ""
    if culprit:
        m = re.search(r"\.(\w+)\s*\(", culprit)
        if m:
            failing_fn = m.group(1)
        elif "." in culprit:
            failing_fn = culprit.split(".")[-1].split("(")[0].strip()
    error_prop = _extract_error_property(error_summary)
    hints = []
    if line_number:
        hints.append(f"**Error occurs at line {line_number}.**")
    if failing_fn:
        hints.append(f"**Failing function:** {failing_fn}")
    if error_prop:
        hints.append(f"**Failing property (add ?. to chain before this):** {error_prop}")
    hint_block = "\n".join(hints) + "\n" if hints else ""
    user_prompt = (
        FIX_USER_PROMPT_TEMPLATE.format(
            error_summary=error_summary,
            stack_trace=stack_trace,
            file_path=str(target_file.relative_to(Path(repo_path))) if repo_path else str(target_file),
            file_content=file_content,
        )
        + hint_block
    )

    try:
        response = call_opus(FIX_SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        return {
            "fix_attempt": fix_attempt,
            "fix_applied": False,
            "fix_failure_reason": f"AI call failed: {e}",
            "validation_log": f"AI call failed: {e}",
        }

    fixed_code = _extract_code_from_response(response)
    if not fixed_code:
        return {
            "fix_attempt": fix_attempt,
            "fix_applied": False,
            "fix_failure_reason": "AI did not return valid code block",
            "validation_log": "AI did not return valid code block",
        }

    if fixed_code.strip() == file_content.strip():
        # Fallback 1: try rule-based on primary file again
        if is_undefined_prop_error and error_prop:
            fixed_content = _apply_optional_chaining_fix(file_content, error_prop)
            if fixed_content and fixed_content != file_content:
                try:
                    target_file.write_text(fixed_content, encoding="utf-8")
                    rel_path = str(target_file.relative_to(Path(repo_path))) if repo_path else str(target_file)
                    return {
                        "fix_attempt": fix_attempt,
                        "fix_applied": True,
                        "file_path": rel_path,
                    }
                except Exception:
                    pass
        # Fallback 2: AI returned same, primary file has no fix — scan OTHER files with error_prop
        if is_undefined_prop_error and error_prop:
            other_files = _find_files_with_property(
                repo_path, error_prop, state.get("search_scope"), target_file
            )
            for other in other_files:
                try:
                    other_content = other.read_text(encoding="utf-8", errors="replace")
                    fixed_content = _apply_optional_chaining_fix(other_content, error_prop)
                    if fixed_content and fixed_content != other_content:
                        other.write_text(fixed_content, encoding="utf-8")
                        rel_path = str(other.relative_to(Path(repo_path))) if repo_path else str(other)
                        return {
                            "fix_attempt": fix_attempt,
                            "fix_applied": True,
                            "file_path": rel_path,
                        }
                except Exception:
                    pass
        return {
            "fix_attempt": fix_attempt,
            "fix_applied": False,
            "fix_failure_reason": "AI returned identical code — no fix applied.",
            "validation_log": "AI returned identical code — no fix applied.",
        }

    try:
        target_file.write_text(fixed_code, encoding="utf-8")
    except Exception as e:
        return {
            "fix_attempt": fix_attempt,
            "fix_applied": False,
            "fix_failure_reason": f"Could not write file: {e}",
            "validation_log": str(e),
        }

    rel_path = str(target_file.relative_to(Path(repo_path))) if repo_path else str(target_file)
    return {
        "fix_attempt": fix_attempt,
        "fix_applied": True,
        "file_path": rel_path,
    }
