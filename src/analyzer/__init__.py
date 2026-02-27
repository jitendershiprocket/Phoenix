"""Repository Analyzer & Diagnostic Module for Project Phoenix.

Scans GitHub repos to identify:
- Angular version
- Node version requirements
- Test/coverage configuration
"""

from .repo_analyzer import RepoAnalyzer, RepoDiagnostics

__all__ = ["RepoAnalyzer", "RepoDiagnostics"]
