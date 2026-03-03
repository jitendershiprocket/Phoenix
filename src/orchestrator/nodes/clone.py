"""Clone Node - Clone repo, checkout branch, create fix branch."""

from __future__ import annotations

import os
import time
from pathlib import Path

import yaml
from git import Repo

from src.orchestrator.state import PhoenixState
from src.services.repo_manager import RepoManager


def _phoenix_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_settings() -> dict:
    """Load paths from config/settings.yaml."""
    config_path = Path(__file__).resolve().parents[3] / "config" / "settings.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def clone_node(state: PhoenixState) -> dict:
    """Clone or fetch repo, checkout branch, create fix branch.
    If local_repo_path is set, use that path directly (no clone) - for fixing local code.
    """
    repo_url = state.get("repo_url", "")
    branch = state.get("branch", "main")
    error_summary = state.get("error_summary", "")
    local_path_raw = state.get("local_repo_path", "")

    if not repo_url:
        return {"repo_path": "", "fix_branch": "", "status": "failed"}

    # Use local repo when configured - pull from upstream (bfrs), cut fix branch from ng_19_9may
    upstream_url = state.get("upstream_url", "")
    if local_path_raw:
        root = _phoenix_root()
        local_path = (root / local_path_raw).resolve()
        if not local_path.exists():
            return {
                "repo_path": "",
                "fix_branch": "",
                "status": "failed",
                "validation_log": f"local_repo_path not found: {local_path}",
            }
        try:
            repo = Repo(local_path)
        except Exception as e:
            return {
                "repo_path": "",
                "fix_branch": "",
                "status": "failed",
                "validation_log": f"local_repo_path is not a git repo: {e}",
            }
        # Fork workflow: use upstream (bfrs) as source of truth when set
        fetch_remote = "upstream"
        if upstream_url:
            if "upstream" not in [r.name for r in repo.remotes]:
                repo.create_remote("upstream", upstream_url)
            try:
                repo.remotes.upstream.fetch()
            except Exception:
                pass
            ref = f"upstream/{branch}"
        else:
            fetch_remote = "origin"
            try:
                repo.remotes.origin.fetch()
            except Exception:
                pass
            ref = f"origin/{branch}"
        try:
            repo.git.checkout(branch)
        except Exception:
            repo.git.checkout("-b", branch, ref)
        try:
            repo.git.reset("--hard", ref)
        except Exception:
            try:
                repo.git.pull(fetch_remote, branch)
            except Exception:
                pass
        ts = int(time.time())
        err_hash = abs(hash((error_summary or "") + repo_url)) % 10000
        fix_branch = f"phoenix/fix-{err_hash}-{ts}"
        try:
            repo.delete_head(fix_branch, force=True)
        except Exception:
            pass
        repo.git.checkout("-b", fix_branch)
        return {"repo_path": str(local_path), "fix_branch": fix_branch}

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
