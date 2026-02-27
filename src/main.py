"""Project Phoenix - Entry Point.

Usage (POC):
    python -m src.main --repo https://github.com/org/demo --error "TypeError: ..."
"""

import argparse
from pathlib import Path

from dotenv import load_dotenv

# Load .env from phoenix/ or repo root (GITHUB_TOKEN, ANTHROPIC_API_KEY)
_phoenix_root = Path(__file__).resolve().parent.parent
if not load_dotenv(_phoenix_root / ".env"):
    load_dotenv(_phoenix_root.parent / ".env")

from src.orchestrator import build_phoenix_graph


def main():
    parser = argparse.ArgumentParser(description="Project Phoenix - Self-Healing Agent")
    parser.add_argument("--repo", required=True, help="Repo URL to fix")
    parser.add_argument("--error", required=True, help="Error message or stack trace")
    parser.add_argument("--branch", default="main", help="Target branch")
    args = parser.parse_args()

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
