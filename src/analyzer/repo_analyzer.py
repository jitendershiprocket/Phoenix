"""Repository Analyzer & Diagnostic Module.

Uses GitHub API to scan repos and extract:
- Angular version (from package.json)
- Node version requirements (engines.node, .nvmrc)
- Test/coverage configuration presence
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from github import Github
from github.Repository import Repository


@dataclass
class RepoDiagnostics:
    """Diagnostic report for a single repository."""

    name: str
    url: str
    default_branch: str
    angular_version: str | None = None
    angular_major: int | None = None  # e.g. 17
    node_version: str | None = None   # From engines.node or .nvmrc
    node_version_file: str | None = None  # .nvmrc, .node-version, etc.
    package_manager: str = "npm"      # npm, yarn, pnpm
    has_angular_json: bool = False
    has_karma: bool = False
    has_jest: bool = False
    has_coverage_config: bool = False
    coverage_command: str | None = None  # e.g. "ng test --code-coverage"
    typescript_version: str | None = None
    is_angular_js: bool = False
    errors: list[str] = field(default_factory=list)


class RepoAnalyzer:
    """Analyzes GitHub repositories for Angular/Node metadata."""

    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GITHUB_TOKEN required. Set env or pass token=...")
        self._gh = Github(self.token)

    def get_repo(self, url_or_slug: str) -> Repository:
        """Resolve repo from URL or owner/name slug."""
        if url_or_slug.startswith("http"):
            # https://github.com/owner/repo or https://github.com/owner/repo.git
            parts = url_or_slug.rstrip("/").replace(".git", "").split("/")
            slug = "/".join(parts[-2:])
        else:
            slug = url_or_slug
        return self._gh.get_repo(slug)

    def _get_file_content(self, repo: Repository, path: str, ref: str) -> str | None:
        """Fetch file content from default branch."""
        try:
            f = repo.get_contents(path, ref=ref)
            return f.decoded_content.decode("utf-8", errors="replace")
        except Exception:
            return None

    def _parse_package_json(self, content: str) -> dict[str, Any] | None:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None

    def _extract_angular_version(self, pkg: dict[str, Any]) -> tuple[str | None, int | None]:
        """Extract @angular/core version. Returns (version_str, major_int)."""
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        for key in ("@angular/core", "angular"):
            if key in deps:
                v = deps[key]
                if isinstance(v, str):
                    v = v.strip("^~>=<")
                    major = self._parse_major(v)
                    return (v, major)
        return (None, None)

    def _parse_major(self, version: str) -> int | None:
        """Extract major version number."""
        m = re.match(r"(\d+)", version)
        return int(m.group(1)) if m else None

    def _extract_node_version(self, pkg: dict[str, Any], repo: Repository, ref: str) -> tuple[str | None, str | None]:
        """
        Get Node version from engines.node or .nvmrc / .node-version.
        Returns (version_str, source_file).
        """
        engines = pkg.get("engines", {}) or {}
        node_eng = engines.get("node")
        if node_eng and isinstance(node_eng, str):
            return (node_eng.strip(), "package.json engines.node")

        for path in (".nvmrc", ".node-version"):
            content = self._get_file_content(repo, path, ref)
            if content:
                v = content.strip().splitlines()[0].strip()
                if v:
                    return (v, path)
        return (None, None)

    def analyze(self, repo_url: str, branch: str | None = None) -> RepoDiagnostics:
        """
        Analyze a single repository. Returns RepoDiagnostics.
        """
        repo = self.get_repo(repo_url)
        ref = branch or repo.default_branch
        diag = RepoDiagnostics(
            name=repo.name,
            url=repo.html_url,
            default_branch=ref,
        )

        # package.json
        pkg_content = self._get_file_content(repo, "package.json", ref)
        if not pkg_content:
            diag.errors.append("package.json not found")
            return diag

        pkg = self._parse_package_json(pkg_content)
        if not pkg:
            diag.errors.append("package.json invalid JSON")
            return diag

        # Angular
        angular_ver, angular_major = self._extract_angular_version(pkg)
        diag.angular_version = angular_ver
        diag.angular_major = angular_major
        if angular_major and angular_major == 1:
            diag.is_angular_js = True

        # angular.json
        diag.has_angular_json = self._get_file_content(repo, "angular.json", ref) is not None

        # Node
        node_ver, node_src = self._extract_node_version(pkg, repo, ref)
        diag.node_version = node_ver
        diag.node_version_file = node_src

        # Package manager
        if self._get_file_content(repo, "yarn.lock", ref):
            diag.package_manager = "yarn"
        elif self._get_file_content(repo, "pnpm-lock.yaml", ref):
            diag.package_manager = "pnpm"

        # TypeScript
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        if "typescript" in deps:
            diag.typescript_version = str(deps["typescript"]).strip("^~")

        # Test & coverage
        diag.has_karma = "karma" in deps or "karma-jasmine" in deps
        diag.has_jest = "jest" in deps or "@jest/core" in deps
        if diag.has_angular_json:
            diag.has_coverage_config = True
            diag.coverage_command = "ng test --code-coverage"
        elif diag.has_jest:
            diag.has_coverage_config = True
            diag.coverage_command = "npm test -- --coverage"
        elif diag.has_karma:
            diag.has_coverage_config = True
            diag.coverage_command = "ng test --code-coverage"

        return diag

    def analyze_all(self, repos: list[dict]) -> list[RepoDiagnostics]:
        """Analyze multiple repos from config format: [{name, url, default_branch?}]."""
        results = []
        for r in repos:
            url = r.get("url", "")
            branch = r.get("default_branch")
            try:
                diag = self.analyze(url, branch)
            except Exception as e:
                diag = RepoDiagnostics(
                    name=r.get("name", "unknown"),
                    url=url,
                    default_branch=branch or "main",
                    errors=[str(e)],
                )
            results.append(diag)
        return results


def format_report(diagnostics: list[RepoDiagnostics], verbose: bool = False) -> str:
    """Format diagnostics as a readable report."""
    lines = [
        "=" * 70,
        "Project Phoenix — Repository Diagnostic Report",
        "=" * 70,
    ]
    for d in diagnostics:
        lines.append(f"\n📦 {d.name}")
        lines.append(f"   URL: {d.url}")
        lines.append(f"   Branch: {d.default_branch}")
        if d.errors:
            lines.append(f"   ❌ Errors: {', '.join(d.errors)}")
        else:
            angular_info = f"Angular {d.angular_version} (v{d.angular_major})" if d.angular_version else "Not Angular"
            if d.is_angular_js:
                angular_info += " [AngularJS]"
            lines.append(f"   Angular: {angular_info}")
            lines.append(f"   Node: {d.node_version or 'Not specified'} ({d.node_version_file or '-'})")
            lines.append(f"   Package manager: {d.package_manager}")
            if d.typescript_version:
                lines.append(f"   TypeScript: {d.typescript_version}")
            lines.append(f"   angular.json: {'✓' if d.has_angular_json else '✗'}")
            lines.append(f"   Test: Karma={d.has_karma}, Jest={d.has_jest}")
            lines.append(f"   Coverage config: {'✓' if d.has_coverage_config else '✗'} {d.coverage_command or ''}")
        if verbose and d.errors:
            for e in d.errors:
                lines.append(f"      - {e}")
    lines.append("\n" + "=" * 70)
    return "\n".join(lines)
