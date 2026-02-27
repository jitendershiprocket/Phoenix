"""Clone Node - Clone repo, checkout branch, create fix branch."""

from __future__ import annotations

import os
import time
from pathlib import Path

import yaml

from src.orchestrator.state import PhoenixState
from src.services.repo_manager import RepoManager


def _load_settings() -> dict:
    """Load paths from config/settings.yaml."""
    config_path = Path(__file__).resolve().parents[3] / "config" / "settings.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def clone_node(state: PhoenixState) -> dict:
    """Clone or fetch repo, checkout branch, create fix branch."""
    repo_url = state.get("repo_url", "")
    branch = state.get("branch", "main")
    error_summary = state.get("error_summary", "")

    if not repo_url:
        return {"repo_path": "", "fix_branch": "", "status": "failed"}

    settings = _load_settings()
    paths = settings.get("paths", {})
    work_dir_raw = paths.get("work_dir", "workspace")
    # Resolve relative to phoenix root (not cwd) - always use phoenix/workspace
    phoenix_root = Path(__file__).resolve().parents[3]
    work_dir = (phoenix_root / work_dir_raw).resolve() if not Path(work_dir_raw).is_absolute() else Path(work_dir_raw)
    cache_repos = paths.get("cache_repos", True)

    # Fix branch name: unique per run (timestamp) + error hash
    ts = int(time.time())
    err_hash = abs(hash((error_summary or "") + repo_url)) % 10000
    fix_branch = f"phoenix/fix-{err_hash}-{ts}"

    manager = RepoManager(work_dir=work_dir, cache_repos=cache_repos)
    token = os.getenv("GITHUB_TOKEN")

    try:
        repo_path, fix_branch = manager.clone_or_fetch(
            repo_url=repo_url,
            branch=branch,
            fix_branch=fix_branch,
            token=token,
        )
        return {"repo_path": repo_path, "fix_branch": fix_branch}
    except Exception as e:
        return {
            "repo_path": "",
            "fix_branch": "",
            "status": "failed",
            "validation_log": str(e),
        }
