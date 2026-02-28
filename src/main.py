"""Project Phoenix - Entry Point.

Usage:
  # Manual: pass error
  python -m src.main --repo URL --error "TypeError: ..."

  # From Sentry: fetch latest bug automatically
  python -m src.main --from-sentry
"""

import argparse
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Load .env from phoenix/ or repo root
_phoenix_root = Path(__file__).resolve().parent.parent
if not load_dotenv(_phoenix_root / ".env"):
    load_dotenv(_phoenix_root.parent / ".env")

from src.orchestrator import build_phoenix_graph
from src.services.sentry_client import SentryBugDetails, fetch_latest_bug


def _load_config() -> dict:
    config_path = _phoenix_root / "config" / "settings.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def _get_repo_url_for_sentry(project_slug: str) -> str:
    """Get repo URL: SENTRY_REPO_URL env, or repos.yaml (name matches SENTRY_PROJECT)."""
    import os
    env_url = os.getenv("SENTRY_REPO_URL")
    if env_url:
        return env_url
    repos_path = _phoenix_root / "config" / "repos.yaml"
    if repos_path.exists():
        with open(repos_path) as f:
            data = yaml.safe_load(f) or {}
        for r in data.get("repos", []):
            if r.get("name", "").lower() == project_slug.lower():
                return r.get("url", "")
            if project_slug and not data.get("repos"):
                break
        repos = data.get("repos", [])
        if repos:
            return repos[0].get("url", "")
    return ""


def main():
    parser = argparse.ArgumentParser(description="Project Phoenix - Self-Healing Agent")
    parser.add_argument("--repo", help="Repo URL to fix")
    parser.add_argument("--error", help="Error message or stack trace (manual mode)")
    parser.add_argument("--branch", default="main", help="Target branch")
    parser.add_argument(
        "--from-sentry",
        action="store_true",
        help="Fetch latest bug from Sentry and resolve (no --repo/--error needed)",
    )
    args = parser.parse_args()
    bug = None

    if args.from_sentry:
        import os

        org = os.getenv("SENTRY_ORG")
        project = os.getenv("SENTRY_PROJECT")
        if not org or not project:
            print("Error: SENTRY_ORG and SENTRY_PROJECT required in .env for --from-sentry")
            return

        print("\n🔄 Fetching latest bug from Sentry...")
        bug = fetch_latest_bug(org, project)
        if not bug:
            print("No unresolved issues in Sentry.")
            return

        repo_url = _get_repo_url_for_sentry(project)
        if not repo_url:
            print("Error: Set SENTRY_REPO_URL in .env or add project to config/repos.yaml")
            return

        # Show bug details
        print("\n" + "=" * 60)
        print("📋 SENTRY BUG (Phoenix will resolve this)")
        print("=" * 60)
        print(f"Issue ID:     {bug.short_id}")
        print(f"Title:        {bug.title or '(none)'}")
        print(f"Error:        {bug.error_summary or bug.culprit or '(from culprit)'}")
        print(f"File:         {bug.file_path}:{bug.line_number or '?'}")
        print(f"Culprit:      {bug.culprit}")
        print(f"Last seen:    {bug.last_seen}")
        print(f"Link:         {bug.permalink}")
        print(f"Repo:         {repo_url}")
        print("=" * 60 + "\n")

        error_summary = bug.error_summary or bug.title or bug.culprit or "Unknown error"
        stack_trace = bug.stack_trace or error_summary
        initial_state = {
            "repo_url": repo_url,
            "branch": args.branch,
            "error_payload": {
                "error_summary": error_summary,
                "file_path": bug.file_path or "",
                "stack_trace": stack_trace,
            },
            "fix_attempt": 0,
            "max_attempts": 3,
        }
    else:
        if not args.repo or not args.error:
            parser.error("Use --repo and --error, or --from-sentry")
            return

        initial_state = {
            "repo_url": args.repo,
            "branch": args.branch,
            "error_payload": {
                "error_summary": args.error,
                "file_path": "",
                "stack_trace": args.error,
            },
            "fix_attempt": 0,
            "max_attempts": 3,
        }

    graph = build_phoenix_graph()
    result = graph.invoke(initial_state)

    print("\n--- Phoenix Agent Result ---")
    status = result.get("status", "unknown")
    print(f"Status: {status}")
    if result.get("pr_url"):
        print(f"PR: {result['pr_url']}")
    if args.from_sentry and bug:
        print(f"Sentry issue resolved: {bug.short_id}")
    if status == "aborted":
        fix_applied = result.get("fix_applied", False)
        print(f"Fix applied: {fix_applied}")
        log = result.get("validation_log", "")
        if log:
            print("Validation log (last 500 chars):")
            print(log[-500:] if len(log) > 500 else log)
    return result


if __name__ == "__main__":
    main()
