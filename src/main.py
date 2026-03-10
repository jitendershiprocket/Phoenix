"""Project Phoenix - Entry Point.

Usage:
  # Manual: pass error
  python -m src.main --repo URL --error "TypeError: ..."

  # From Sentry: fetch latest bug automatically
  python -m src.main --from-sentry
"""

import argparse
import atexit
import signal
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


def _get_repo_config_for_sentry(project_slug: str) -> dict:
    """Get repo config from SENTRY_REPO_URL env or repos.yaml.
    Returns dict with url, branch, node_version, angular_version, search_scope."""
    import os
    env_url = os.getenv("SENTRY_REPO_URL")
    if env_url:
        return {
            "url": env_url,
            "branch": os.getenv("SENTRY_BRANCH", "main"),
            "node_version": None,
            "angular_version": None,
            "search_scope": None,
        }

    repos_path = _phoenix_root / "config" / "repos.yaml"
    if repos_path.exists():
        with open(repos_path) as f:
            data = yaml.safe_load(f) or {}
        for r in data.get("repos", []):
            if r.get("name", "").lower() == project_slug.lower():
                out = {
                    "url": r.get("url", ""),
                    "branch": r.get("default_branch", "main"),
                    "node_version": r.get("node_version"),
                    "angular_version": r.get("angular_version"),
                    "search_scope": r.get("search_scope"),
                }
                if r.get("local_repo_path"):
                    out["local_repo_path"] = r["local_repo_path"]
                if r.get("upstream_url"):
                    out["upstream_url"] = r["upstream_url"]
                return out
        repos = data.get("repos", [])
        if repos:
            r = repos[0]
            return {
                "url": r.get("url", ""),
                "branch": r.get("default_branch", "main"),
                "node_version": r.get("node_version"),
                "angular_version": r.get("angular_version"),
                "search_scope": r.get("search_scope"),
            }
    return {"url": "", "branch": "main", "node_version": None, "angular_version": None, "search_scope": None}


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
    parser.add_argument(
        "--project",
        help="Sentry project slug (e.g. seller_19). Uses SENTRY_ORG_<PROJECT>, SENTRY_BASE_URL_<PROJECT> from .env",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Start web dashboard at http://localhost:5050",
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=5050,
        help="Dashboard port (default: 5050)",
    )
    args = parser.parse_args()
    bug = None

    if args.from_sentry:
        import os

        if args.project:
            key = args.project.upper().replace("-", "_")
            org = os.getenv(f"SENTRY_ORG_{key}") or os.getenv("SENTRY_ORG")
            base_url = os.getenv(f"SENTRY_BASE_URL_{key}") or os.getenv("SENTRY_BASE_URL")
            config = _get_repo_config_for_sentry(args.project)
            sentry_slug = args.project
        else:
            org = os.getenv("SENTRY_ORG")
            sentry_slug = os.getenv("SENTRY_PROJECT")
            base_url = os.getenv("SENTRY_BASE_URL")
            config = {}

        if not org or not sentry_slug:
            print("Error: SENTRY_ORG and SENTRY_PROJECT required in .env for --from-sentry (or use --project X with SENTRY_ORG_X, SENTRY_BASE_URL_X)")
            return

        if args.dashboard:
            import time as _time
            from src.dashboard.progress import progress
            from src.dashboard.server import start_dashboard, stop_dashboard
            progress.reset("Fetching bug from Sentry...")
            port = start_dashboard(args.dashboard_port)
            def _on_exit():
                stop_dashboard()
            atexit.register(_on_exit)

            def _sigint_handler(signum, frame):
                stop_dashboard()
                signal.signal(signal.SIGINT, signal.SIG_DFL)
                raise KeyboardInterrupt()
            signal.signal(signal.SIGINT, _sigint_handler)
            print(f"📊 Dashboard: http://localhost:{port}\n")
            print("\n🔄 Fetching latest bug from Sentry...")
            progress.step_start("fetch")
            t0 = _time.time()
        else:
            print("\n🔄 Fetching latest bug from Sentry...")

        bug = fetch_latest_bug(org, sentry_slug, base_url=base_url)

        if args.dashboard:
            progress.step_end("fetch", _time.time() - t0, f"Fetched {bug.short_id}" if bug else "No bug", success=bool(bug))
        if not bug:
            print("No unresolved issues in Sentry.")
            return

        if not config:
            config = _get_repo_config_for_sentry(args.project or sentry_slug)
        repo_url = config.get("url", "")
        branch = config.get("branch", "main")
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
        print(f"Branch:       {branch}  (clone + PR target)")
        print("=" * 60 + "\n")

        if args.dashboard:
            from src.dashboard.progress import progress
            summary = f"{bug.short_id}: {bug.title or bug.error_summary or 'Unknown error'}"[:120]
            progress.set_bug_summary(summary)
            progress.set_bug_details({
                "short_id": bug.short_id,
                "error": bug.error_summary or bug.title or "(no error)",
                "culprit": bug.culprit or "",
                "file": bug.file_path or ":?",
                "link": bug.permalink or "",
            })

        error_summary = bug.error_summary or bug.title or bug.culprit or "Unknown error"
        stack_trace = bug.stack_trace or error_summary
        error_payload = {
            "error_summary": error_summary,
            "file_path": bug.file_path or "",
            "stack_trace": stack_trace,
            "line_number": bug.line_number,
            "culprit": bug.culprit or "",
        }
        if config.get("angular_version"):
            error_payload["angular_version"] = config["angular_version"]
        if config.get("node_version"):
            error_payload["node_version"] = config["node_version"]
        initial_state = {
            "repo_url": repo_url,
            "branch": args.branch if not args.from_sentry else branch,
            "search_scope": config.get("search_scope"),
            "error_payload": error_payload,
            "fix_attempt": 0,
            "max_attempts": 3,
        }
        if config.get("local_repo_path"):
            initial_state["local_repo_path"] = config["local_repo_path"]
        if config.get("upstream_url"):
            initial_state["upstream_url"] = config["upstream_url"]
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

    if args.dashboard and not bug:
        from src.dashboard.progress import progress
        from src.dashboard.server import start_dashboard, stop_dashboard
        progress.reset(args.error or "Manual run")
        start_dashboard(args.dashboard_port)
        atexit.register(stop_dashboard)

        def _sigint(s, f):
            stop_dashboard()
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            raise KeyboardInterrupt()
        signal.signal(signal.SIGINT, _sigint)

    graph = build_phoenix_graph(enable_dashboard=args.dashboard)
    result = graph.invoke(initial_state)

    if args.dashboard:
        import time as _t
        from src.dashboard.progress import progress
        status = result.get("status", "unknown")
        success = status == "success" or (result.get("pr_url") and status not in ("aborted", "failed"))
        progress.set_overall_done(success)
        if result.get("pr_url"):
            progress.set_pr_url(result["pr_url"])
        _t.sleep(6)  # Let UI poll and show success + PR link before process exits

    print("\n--- Phoenix Agent Result ---")
    status = result.get("status", "unknown")
    print(f"Status: {status}")
    if result.get("pr_url"):
        print(f"PR: {result['pr_url']}")
    if args.from_sentry and bug:
        print(f"Sentry issue resolved: {bug.short_id}")
    if status in ("aborted", "failed"):
        fix_applied = result.get("fix_applied", False)
        print(f"Fix applied: {fix_applied}")
        log = result.get("fix_failure_reason") or result.get("validation_log", "")
        if log:
            print("Reason / validation log (last 800 chars):")
            print(log[-800:] if len(log) > 800 else log)
    return result


if __name__ == "__main__":
    main()
