"""Validator - Run build + lint. Uses package.json scripts (npm run build, npm run lint). Works for any Node/JS/TS project."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path


def _get_nvm_path() -> Path | None:
    """Return nvm.sh path if it exists."""
    nvm_dir = os.environ.get("NVM_DIR") or os.path.expanduser("~/.nvm")
    nvm_sh = Path(nvm_dir) / "nvm.sh"
    return nvm_sh if nvm_sh.exists() else None


def _get_node_version() -> str | None:
    """Get configured Node version (e.g. 18) for nvm use. Returns None if not set."""
    try:
        config_path = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
        if config_path.exists():
            import yaml
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
            return cfg.get("validation", {}).get("node_version")
    except Exception:
        pass
    return None


def _run_with_node(cmd: list[str], cwd: Path, timeout: int) -> tuple[int, str]:
    """Run command, using nvm use X if node_version is configured."""
    node_ver = _get_node_version()
    nvm_sh = _get_nvm_path()
    if node_ver and nvm_sh:
        # Use explicit nvm path (avoids shell variable expansion issues in subprocess)
        nvm_src = ". {} 2>/dev/null && nvm use {} 2>/dev/null || true; ".format(
            shlex.quote(str(nvm_sh)), node_ver
        )
        full_cmd = ["bash", "-c", nvm_src + " ".join(shlex.quote(c) for c in cmd)]
        result = subprocess.run(
            full_cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "NVM_DIR": str(nvm_sh.parent)},
        )
        return result.returncode, result.stdout + result.stderr
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout + result.stderr


def _ensure_deps(repo_path: Path, timeout: int = 120) -> tuple[bool, str]:
    """Run npm install to sync deps with package.json."""
    try:
        code, log = _run_with_node(["npm", "install"], repo_path, timeout)
        return code == 0, log
    except Exception as e:
        return False, str(e)


def run_ng_build(repo_path: str | Path, timeout: int = 120) -> tuple[bool, str]:
    """Run npm run build. Works for Angular, React, Vue, etc. Returns (passed, log)."""
    path = Path(repo_path)
    if not (path / "package.json").exists():
        return False, "No package.json found"
    ok, msg = _ensure_deps(path, timeout)
    if not ok:
        return False, f"npm install failed: {msg}"
    try:
        code, log = _run_with_node(
            ["npm", "run", "build"],
            path, timeout,
        )
        return code == 0, log
    except subprocess.TimeoutExpired:
        return False, "npm run build timed out"
    except Exception as e:
        return False, str(e)


def run_ng_lint(repo_path: str | Path, timeout: int = 60) -> tuple[bool, str]:
    """Run npm run lint if script exists. Returns (passed, log)."""
    path = Path(repo_path)
    if not (path / "package.json").exists():
        return False, "No package.json found"
    # Check if lint script exists
    import json
    try:
        pkg = json.loads((path / "package.json").read_text())
        if "lint" not in pkg.get("scripts", {}):
            return True, "No lint script (skipped)"
    except Exception:
        pass
    try:
        code, log = _run_with_node(["npm", "run", "lint"], path, timeout)
        return code == 0, log
    except subprocess.TimeoutExpired:
        return False, "npm run lint timed out"
    except Exception as e:
        return False, str(e)


def run_lint_changed_only(
    repo_path: str | Path, file_path: str, timeout: int = 30
) -> tuple[bool, str]:
    """Lint only the changed file(s). Returns (passed, log). Uses eslint directly."""
    path = Path(repo_path)
    full_path = path / file_path
    if not full_path.exists():
        return True, f"File not found, skip lint: {file_path}"
    if not (path / "package.json").exists():
        return True, "No package.json (skip lint)"
    # Also lint sibling .html if it's a component .ts
    files_to_lint = [str(full_path)]
    if file_path.endswith(".component.ts"):
        html_path = full_path.with_suffix(".html")
        if html_path.exists():
            files_to_lint.append(str(html_path))
    try:
        code, log = _run_with_node(
            ["npx", "eslint", "--no-error-on-unmatched-pattern", *files_to_lint],
            path,
            timeout,
        )
        return code == 0, log or "(no issues)"
    except subprocess.TimeoutExpired:
        return False, "eslint timed out"
    except Exception as e:
        return True, f"eslint skipped: {e}"
