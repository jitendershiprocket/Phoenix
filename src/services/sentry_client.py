"""Sentry API Client - Fetch latest issues/events for Phoenix."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class SentryBugDetails:
    """Parsed bug details from Sentry for Phoenix fix flow."""

    issue_id: str
    short_id: str
    title: str
    error_summary: str
    stack_trace: str
    file_path: str
    line_number: int | None
    culprit: str
    permalink: str
    last_seen: str


def _build_stack_trace(entries: list[dict]) -> str:
    """Extract stack trace string from Sentry event entries."""
    lines: list[str] = []
    for entry in entries:
        if entry.get("type") != "exception":
            continue
        for exc in entry.get("values", []):
            exc_type = exc.get("type", "Error")
            exc_value = exc.get("value", "")
            lines.append(f"{exc_type}: {exc_value}")
            for frame in reversed(exc.get("stacktrace", {}).get("frames", [])):
                fn = frame.get("function", "?")
                fn_file = frame.get("filename", frame.get("absPath", "?"))
                ln = frame.get("lineNo")
                col = frame.get("colNo")
                loc = f"{fn_file}:{ln}:{col}" if ln else fn_file
                lines.append(f"  at {fn} ({loc})")
    return "\n".join(lines) if lines else ""


def _normalize_sentry_path(path: str) -> str:
    """Extract usable path from webpack/sentry paths. e.g. webpack:///./src/... -> src/..."""
    if not path:
        return ""
    # e.g. webpack-internal:///./src/... or ~/app/...
    for prefix in ("webpack-internal:///", "webpack:///", "~/"):
        if path.startswith(prefix):
            path = path.replace(prefix, "").lstrip("./")
            break
    return path


def _extract_file_and_line(entries: list[dict]) -> tuple[str, int | None]:
    """Get first in-app frame, else first frame with .ts/.tsx/.js filename."""
    best: tuple[str, int | None] = ("", None)
    for entry in entries:
        if entry.get("type") != "exception":
            continue
        for exc in entry.get("values", []):
            for frame in exc.get("stacktrace", {}).get("frames", []):
                fn = frame.get("filename", "") or frame.get("absPath", "")
                ln = frame.get("lineNo")
                if not fn:
                    continue
                fn = _normalize_sentry_path(fn)
                if not fn:
                    continue
                # Prefer in-app, or .ts/.tsx source files
                if frame.get("inApp"):
                    return (fn, ln)
                if not best[0] and (".ts" in fn or ".tsx" in fn or "src" in fn):
                    best = (fn, ln)
    return best if best[0] else ("", None)


def fetch_latest_bug(
    org_slug: str,
    project_slug: str,
    token: str | None = None,
    base_url: str | None = None,
) -> SentryBugDetails | None:
    """
    Fetch the latest unresolved issue from Sentry.
    Returns parsed bug details for Phoenix, or None if no issues.
    """
    token = token or os.getenv("SENTRY_AUTH_TOKEN")
    if not token:
        raise ValueError("SENTRY_AUTH_TOKEN required for --from-sentry")

    # Custom subdomain: https://shiprocket-1s.sentry.io or default sentry.io
    base_raw = base_url or os.getenv("SENTRY_BASE_URL") or "https://sentry.io"
    base_raw = base_raw.rstrip("/")
    base = f"{base_raw}/api/0" if "/api" not in base_raw else base_raw
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(timeout=30.0) as client:
        # 1. List project issues (latest first)
        r = client.get(
            f"{base}/projects/{org_slug}/{project_slug}/issues/",
            headers=headers,
            params={"query": "is:unresolved", "statsPeriod": "14d"},
        )
        r.raise_for_status()
        issues = r.json()
        if not issues:
            return None

        issue = issues[0]
        issue_id = issue["id"]
        short_id = issue.get("shortId", issue_id)
        meta = issue.get("metadata") or {}
        title = meta.get("title") or issue.get("title") or "Unknown"
        culprit = issue.get("culprit") or ""
        permalink = issue.get("permalink", "")
        last_seen = issue.get("lastSeen", "")

        # 2. Get latest event for stack trace
        r2 = client.get(
            f"{base}/organizations/{org_slug}/issues/{issue_id}/events/latest/",
            headers=headers,
        )
        r2.raise_for_status()
        event = r2.json()

        entries = event.get("entries", [])
        stack_trace = _build_stack_trace(entries)
        file_path, line_number = _extract_file_and_line(entries)
        # Include culprit for fix node file resolution
        if culprit and culprit not in (stack_trace or ""):
            stack_trace = f"{culprit}\n{stack_trace}" if stack_trace else culprit

        # Error summary from exception entries or title
        error_summary = title or culprit or "Unknown error"
        for entry in entries:
            if entry.get("type") == "exception":
                for exc in entry.get("values", []):
                    exc_type = exc.get("type", "Error")
                    exc_val = exc.get("value", "")
                    if exc_val:
                        error_summary = f"{exc_type}: {exc_val}"
                    elif exc_type:
                        error_summary = exc_type
                    break
                break

        return SentryBugDetails(
            issue_id=issue_id,
            short_id=short_id,
            title=title,
            error_summary=error_summary,
            stack_trace=stack_trace or error_summary,
            file_path=file_path,
            line_number=line_number,
            culprit=culprit,
            permalink=permalink,
            last_seen=last_seen,
        )
