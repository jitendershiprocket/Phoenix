#!/usr/bin/env python3
"""CLI entry point for Repository Analyzer & Diagnostic Module.

Usage:
  python scripts/run_repo_analyzer.py                    # Uses config/repos.yaml
  python scripts/run_repo_analyzer.py --repo URL [URL2]  # Scan specific repos
  python scripts/run_repo_analyzer.py --verbose
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Phoenix root (phoenix/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env from phoenix/ or repo root
from dotenv import load_dotenv
if not load_dotenv(PROJECT_ROOT / ".env"):
    load_dotenv(PROJECT_ROOT.parent / ".env")

import yaml
from src.analyzer.repo_analyzer import RepoAnalyzer, RepoDiagnostics, format_report


def load_repos_from_config() -> list[dict]:
    """Load repo list from config/repos.yaml."""
    config_path = PROJECT_ROOT / "config" / "repos.yaml"
    if not config_path.exists():
        return []
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return data.get("repos", [])


def main() -> int:
    parser = argparse.ArgumentParser(description="Project Phoenix — Repo Analyzer")
    parser.add_argument("--repo", "-r", action="append", help="Repo URL(s) to scan")
    parser.add_argument("--config", "-c", action="store_true", help="Use config/repos.yaml (default if no --repo)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    repos: list[dict] = []
    if args.repo:
        for url in args.repo:
            name = url.rstrip("/").split("/")[-1].replace(".git", "")
            repos.append({"name": name, "url": url, "default_branch": "main"})
    else:
        repos = load_repos_from_config()
        if not args.config and not repos:
            parser.error("No repos. Use --repo URL or add repos to config/repos.yaml")

    if not repos:
        print("No repositories configured.")
        return 1

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN environment variable required.", file=sys.stderr)
        return 1

    try:
        analyzer = RepoAnalyzer(token=token)
        results = analyzer.analyze_all(repos)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        import json
        out = []
        for d in results:
            out.append({
                "name": d.name,
                "url": d.url,
                "default_branch": d.default_branch,
                "angular_version": d.angular_version,
                "angular_major": d.angular_major,
                "node_version": d.node_version,
                "node_version_file": d.node_version_file,
                "package_manager": d.package_manager,
                "has_angular_json": d.has_angular_json,
                "has_karma": d.has_karma,
                "has_jest": d.has_jest,
                "has_coverage_config": d.has_coverage_config,
                "coverage_command": d.coverage_command,
                "typescript_version": d.typescript_version,
                "is_angular_js": d.is_angular_js,
                "errors": d.errors,
            })
        print(json.dumps(out, indent=2))
    else:
        print(format_report(results, verbose=args.verbose))

    return 0


if __name__ == "__main__":
    sys.exit(main())
