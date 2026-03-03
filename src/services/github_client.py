"""GitHub Client - Commit, push, create PR."""

from __future__ import annotations

import os
from pathlib import Path

from git import Repo
from github import Github


def _repo_slug_from_url(url: str) -> str:
    """Extract owner/repo from URL."""
    url = url.rstrip("/").replace(".git", "")
    parts = [p for p in url.split("/") if p and p != "https:" and p != "http:"]
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return ""


def commit_and_push(
    repo_path: str | Path,
    fix_branch: str,
    commit_message: str,
    token: str | None = None,
    push_remote: str = "origin",
) -> tuple[bool, str]:
    """Commit all changes and push fix_branch. Returns (success, message).
    push_remote: 'origin' or 'upstream' — push to this remote.
    """
    token = token or os.getenv("GITHUB_TOKEN")
    path = Path(repo_path)
    if not (path / ".git").exists():
        return False, "Not a git repo"

    try:
        repo = Repo(path)
        # Ensure we're on fix_branch
        if repo.head.ref.name != fix_branch:
            repo.git.checkout(fix_branch)

        # Set git user for commit (required)
        with repo.config_writer() as cw:
            cw.set_value("user", "name", "Project Phoenix")
            cw.set_value("user", "email", "phoenix@shiprocket.dev")

        # Add all changes, check we have something to commit
        repo.git.add(".")
        staged = repo.git.diff("--cached", "--name-only")
        if not staged.strip():
            return False, "No changes to commit (fix may already be in main, or file resolution failed)"
        try:
            repo.index.commit(commit_message)
        except Exception as e:
            err_lower = str(e).lower()
            if "nothing to commit" in err_lower or "no changes" in err_lower:
                return False, "No changes to commit"
            raise

        # Push to specified remote (origin or upstream)
        remote = repo.remotes[push_remote]
        url = remote.url
        push_spec = f"HEAD:{fix_branch}"
        if token and url.startswith("https://") and token not in url:
            auth_url = url.replace("https://", f"https://{token}@", 1)
            repo.git.push(auth_url, push_spec)
        else:
            remote.push(refspec=push_spec)

        return True, "Pushed"
    except Exception as e:
        return False, str(e)


def create_pull_request(
    repo_url: str,
    fix_branch: str,
    base_branch: str,
    title: str,
    body: str,
    token: str | None = None,
) -> tuple[str | None, str]:
    """Create PR via GitHub API. Returns (pr_url, error_message)."""
    token = token or os.getenv("GITHUB_TOKEN")
    if not token:
        return None, "GITHUB_TOKEN required"

    slug = _repo_slug_from_url(repo_url)
    if not slug:
        return None, "Invalid repo URL"

    try:
        gh = Github(token)
        repo = gh.get_repo(slug)
        pr = repo.create_pull(title=title, body=body, head=fix_branch, base=base_branch)
        return pr.html_url, ""
    except Exception as e:
        return None, str(e)
