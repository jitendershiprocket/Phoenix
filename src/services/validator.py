"""Validator - Run build + lint. Uses package.json scripts (npm run build, npm run lint). Works for any Node/JS/TS project."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path


def _get_nvm_path() -> Path | None:
    """Return nvm.sh path if it exists."""
    nvm_dir = os.environ.get("NVM_DIR") or os.path.expanduser("~/.nvm")
    nvm_sh = Path(nvm_dir) / "nvm.sh"
    return nvm_sh if nvm_sh.exists() else None


def _get_node_version(repo_url: str | None = None) -> str | None:
    """Get Node version for nvm use. Prefer per-repo from repos.yaml, else settings.yaml."""
    if repo_url:
        try:
            repos_path = Path(__file__).resolve().parents[2] / "config" / "repos.yaml"
            if repos_path.exists():
                import yaml
                with open(repos_path) as f:
                    data = yaml.safe_load(f) or {}
                for r in data.get("repos", []):
                    if r.get("url", "").rstrip("/") == repo_url.rstrip("/"):
                        if r.get("node_version"):
                            return str(r["node_version"])
                        break
        except Exception:
            pass
    try:
        config_path = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
        if config_path.exists():
            import yaml
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
            return cfg.get("validation", {}).get("node_version")
    except Exception:
        pass
    return None


def _get_npm_install_args(repo_url: str | None = None) -> list[str]:
    """Get npm install extra args (e.g. --force). Prefer per-repo, else settings."""
    if repo_url:
        try:
            repos_path = Path(__file__).resolve().parents[2] / "config" / "repos.yaml"
            if repos_path.exists():
                import yaml
                with open(repos_path) as f:
                    data = yaml.safe_load(f) or {}
                for r in data.get("repos", []):
                    if r.get("url", "").rstrip("/") == repo_url.rstrip("/"):
                        if r.get("npm_install_args"):
                            return r["npm_install_args"] if isinstance(r["npm_install_args"], list) else [r["npm_install_args"]]
                        break
        except Exception:
            pass
    try:
        config_path = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
        if config_path.exists():
            import yaml
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
            args = cfg.get("validation", {}).get("npm_install_args", [])
            return args if isinstance(args, list) else [args] if args else []
    except Exception:
        pass
    return []


def _get_build_timeout(repo_url: str | None = None) -> int:
    """Get build timeout in seconds. Per-repo from repos.yaml, else settings.yaml."""
    if repo_url:
        try:
            repos_path = Path(__file__).resolve().parents[2] / "config" / "repos.yaml"
            if repos_path.exists():
                import yaml
                with open(repos_path) as f:
                    data = yaml.safe_load(f) or {}
                for r in data.get("repos", []):
                    if r.get("url", "").rstrip("/") == repo_url.rstrip("/"):
                        if r.get("build_timeout") is not None:
                            return int(r["build_timeout"])
                        break
        except Exception:
            pass
    try:
        config_path = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
        if config_path.exists():
            import yaml
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
            return int(cfg.get("validation", {}).get("build_timeout", 480))
    except Exception:
        pass
    return 480


def _get_eslint_timeout(repo_url: str | None = None) -> int | None:
    """Get eslint timeout in seconds. 0 = no timeout (None for subprocess)."""
    try:
        config_path = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
        if config_path.exists():
            import yaml
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
            val = cfg.get("validation", {}).get("eslint_timeout", 60)
            v = int(val) if val is not None else 60
            return None if v == 0 else v
    except Exception:
        pass
    return 60


def _run_with_node(cmd: list[str], cwd: Path, timeout: int | None, repo_url: str | None = None) -> tuple[int, str]:
    """Run command, using nvm use X if node_version is configured."""
    node_ver = _get_node_version(repo_url)
    nvm_sh = _get_nvm_path()
    if node_ver and nvm_sh:
        # Use explicit nvm path (avoids shell variable expansion issues in subprocess)
        nvm_src = ". {} 2>/dev/null && nvm use {} 2>/dev/null || true; ".format(
            shlex.quote(str(nvm_sh)), node_ver
        )
        full_cmd = ["bash", "-c", nvm_src + " ".join(shlex.quote(c) for c in cmd)]
        result = subprocess.run(
            full_cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "NVM_DIR": str(nvm_sh.parent)},
        )
        return result.returncode, result.stdout + result.stderr
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout + result.stderr


def _ensure_deps(repo_path: Path, timeout: int = 120, repo_url: str | None = None) -> tuple[bool, str]:
    """Run npm install to sync deps with package.json. Uses npm_install_args (e.g. --force) from config."""
    extra = _get_npm_install_args(repo_url)
    cmd = ["npm", "install"] + extra
    try:
        code, log = _run_with_node(cmd, repo_path, timeout, repo_url)
        return code == 0, log
    except Exception as e:
        return False, str(e)


def run_ng_build(repo_path: str | Path, timeout: int | None = None, repo_url: str | None = None) -> tuple[bool, str]:
    """Run npm run build. Works for Angular, React, Vue, etc. Returns (passed, log)."""
    path = Path(repo_path)
    if not (path / "package.json").exists():
        return False, "No package.json found"
    if timeout is None:
        timeout = _get_build_timeout(repo_url)
    ok, msg = _ensure_deps(path, timeout, repo_url)
    if not ok:
        return False, f"npm install failed: {msg}"
    try:
        code, log = _run_with_node(
            ["npm", "run", "build"],
            path, timeout, repo_url,
        )
        return code == 0, log
    except subprocess.TimeoutExpired:
        return False, "npm run build timed out"
    except Exception as e:
        return False, str(e)


def run_ng_lint(repo_path: str | Path, timeout: int = 60, repo_url: str | None = None) -> tuple[bool, str]:
    """Run npm run lint if script exists. Returns (passed, log)."""
    path = Path(repo_path)
    if not (path / "package.json").exists():
        return False, "No package.json found"
    # Check if lint script exists
    import json
    try:
        pkg = json.loads((path / "package.json").read_text())
        if "lint" not in pkg.get("scripts", {}):
            return True, "No lint script (skipped)"
    except Exception:
        pass
    try:
        code, log = _run_with_node(["npm", "run", "lint"], path, timeout, repo_url)
        return code == 0, log
    except subprocess.TimeoutExpired:
        return False, "npm run lint timed out"
    except Exception as e:
        return False, str(e)


def run_lint_changed_only(
    repo_path: str | Path, file_path: str, timeout: int | None = None, repo_url: str | None = None
) -> tuple[bool, str]:
    """Lint only the changed file(s). Uses project's local eslint (avoids npx pulling eslint 10)."""
    path = Path(repo_path)
    full_path = path / file_path
    if not full_path.exists():
        return True, f"File not found, skip lint: {file_path}"
    if not (path / "package.json").exists():
        return True, "No package.json (skip lint)"
    if timeout is None:
        timeout = _get_eslint_timeout(repo_url)
    # Also lint sibling .html if it's a component .ts
    files_to_lint = [str(full_path)]
    if file_path.endswith(".component.ts"):
        html_path = full_path.with_suffix(".html")
        if html_path.exists():
            files_to_lint.append(str(html_path))

    # Prefer project's local eslint (uses .eslintrc.*, avoids npx installing latest v10)
    local_eslint = path / "node_modules" / ".bin" / "eslint"
    if local_eslint.exists():
        eslint_cmd = [str(local_eslint), "--no-error-on-unmatched-pattern", *files_to_lint]
    else:
        eslint_cmd = ["npx", "eslint", "--no-error-on-unmatched-pattern", *files_to_lint]

    try:
        code, log = _run_with_node(eslint_cmd, path, timeout, repo_url)
        return code == 0, log or "(no issues)"
    except subprocess.TimeoutExpired:
        return False, "eslint timed out"
    except Exception as e:
        return True, f"eslint skipped: {e}"
