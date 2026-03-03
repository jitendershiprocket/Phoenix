"""Repo Manager - Clone, checkout, create branch for Project Phoenix."""

from __future__ import annotations

import os
import re
from pathlib import Path

from git import Repo
from git.exc import GitCommandError


def _repo_name_from_url(url: str) -> str:
    """Extract repo name from URL. e.g. github.com/owner/repo -> repo"""
    url = url.rstrip("/").replace(".git", "")
    parts = url.split("/")
    return parts[-1] if parts else "repo"


def _auth_url(url: str, token: str | None) -> str:
    """Add token to URL for private repo clone. https://github.com/owner/repo -> https://TOKEN@github.com/owner/repo"""
    if not token:
        return url
    # https://github.com/... or git@github.com:...
    if url.startswith("https://"):
        return url.replace("https://", f"https://{token}@", 1)
    if url.startswith("http://"):
        return url.replace("http://", f"http://{token}@", 1)
    return url


class RepoManager:
    """Clone repos, checkout branches, create fix branches."""

    def __init__(self, work_dir: str | Path = "workspace", cache_repos: bool = True):
        self.work_dir = Path(work_dir)
        self.cache_repos = cache_repos
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def clone_or_fetch(
        self,
        repo_url: str,
        branch: str = "main",
        fix_branch: str | None = None,
        token: str | None = None,
    ) -> tuple[str, str]:
        """
        Clone repo (or fetch if cached), checkout branch, create fix_branch.
        Returns (repo_path, fix_branch_name).
        """
        token = token or os.getenv("GITHUB_TOKEN")
        auth_url = _auth_url(repo_url, token)
        repo_name = _repo_name_from_url(repo_url)
        repo_path = self.work_dir / repo_name

        # Generate fix branch name if not provided
        if not fix_branch:
            fix_branch = f"phoenix/fix-{abs(hash(repo_url + branch)) % 100000}"

        if repo_path.exists() and self.cache_repos:
            # Already cloned - fetch and checkout
            repo = Repo(repo_path)
            try:
                repo.remotes.origin.fetch()
            except GitCommandError:
                pass
            self._checkout_and_branch(repo, branch, fix_branch)
        else:
            # Fresh clone
            Repo.clone_from(
                auth_url,
                repo_path,
                branch=branch,
                depth=1,
            )
            repo = Repo(repo_path)
            self._checkout_and_branch(repo, branch, fix_branch)

        return str(repo_path), fix_branch

    def _checkout_and_branch(
        self,
        repo: Repo,
        base_branch: str,
        fix_branch: str,
    ) -> None:
        """Checkout base branch, create fix branch from it. Reset to clean remote (discard prior local changes)."""
        try:
            repo.git.checkout(base_branch)
        except GitCommandError:
            repo.remotes.origin.fetch(base_branch)
            repo.git.checkout("-B", base_branch, f"origin/{base_branch}")
        try:
            repo.remotes.origin.fetch()
            repo.git.reset("--hard", f"origin/{base_branch}")
        except Exception:
            try:
                repo.git.pull("origin", base_branch)
            except Exception:
                pass
        # Delete fix_branch if exists, create fresh
        try:
            repo.delete_head(fix_branch, force=True)
        except Exception:
            pass
        repo.git.checkout("-b", fix_branch)
