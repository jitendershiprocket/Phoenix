"""Validator - Run ng test and ng lint in repo."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _ensure_deps(repo_path: Path, timeout: int = 120) -> tuple[bool, str]:
    """Run npm install if node_modules missing."""
    if (repo_path / "node_modules").exists():
        return True, ""
    try:
        result = subprocess.run(
            ["npm", "install"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def run_ng_test(repo_path: str | Path, timeout: int = 120) -> tuple[bool, str]:
    """Run ng test (Karma). Returns (passed, log)."""
    path = Path(repo_path)
    if not (path / "package.json").exists():
        return False, "No package.json found"
    ok, msg = _ensure_deps(path, timeout)
    if not ok:
        return False, f"npm install failed: {msg}"
    try:
        result = subprocess.run(
            ["npm", "run", "test", "--", "--no-watch", "--browsers=ChromeHeadless"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        log = result.stdout + result.stderr
        return result.returncode == 0, log
    except subprocess.TimeoutExpired:
        return False, "ng test timed out"
    except Exception as e:
        return False, str(e)


def run_ng_lint(repo_path: str | Path, timeout: int = 60) -> tuple[bool, str]:
    """Run ng lint. Returns (passed, log)."""
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
        result = subprocess.run(
            ["npm", "run", "lint"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        log = result.stdout + result.stderr
        return result.returncode == 0, log
    except subprocess.TimeoutExpired:
        return False, "ng lint timed out"
    except Exception as e:
        return False, str(e)
