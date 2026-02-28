# Project Phoenix

**Self-Healing Autonomous AI Agent** for Shiprocket Frontend Engineering.

Reduces tech debt and auto-fixes production issues → tests → raises PR.

---

## Quick Start (POC)

Run from `opus_4.6/phoenix/` or `opus_4.6`:

```bash
cd opus_4.6/phoenix
python -m venv ../venv
source ../venv/bin/activate  # Windows: ..\venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # Add ANTHROPIC_API_KEY, GITHUB_TOKEN
```

```bash
# Manual mode
python -m src.main --repo https://github.com/jitendershiprocket/demo-app \
  --error "TypeError: Cannot read properties of undefined (reading 'id')"

# From Sentry: fetch latest bug automatically
python -m src.main --from-sentry
```

**Sentry mode** requires in `.env`:
- `SENTRY_AUTH_TOKEN` - from sentry.io → Settings → Auth Tokens
- `SENTRY_ORG` - org slug (from Sentry URL)
- `SENTRY_PROJECT` - project slug (must match repos.yaml or use SENTRY_REPO_URL)
- `SENTRY_REPO_URL` - (optional) GitHub repo URL; else use `config/repos.yaml`

### Repository Analyzer (Diagnostic Module)

Scan all configured repos for Angular version, Node version, and test/coverage config:

```bash
# Use config/repos.yaml
python scripts/run_repo_analyzer.py

# Scan specific repos
python scripts/run_repo_analyzer.py --repo https://github.com/org/repo1 --repo https://github.com/org/repo2

# JSON output
python scripts/run_repo_analyzer.py --json
```

Requires `GITHUB_TOKEN` in `.env`.

---

## Production Setup

Phoenix has **no hardcoded project references**. For prod:

1. **Option A (single repo):** Set in `.env`:
   - `SENTRY_ORG`, `SENTRY_PROJECT`, `SENTRY_AUTH_TOKEN`
   - `SENTRY_REPO_URL=https://github.com/your-org/your-repo`

2. **Option B (multi-repo):** Add to `config/repos.yaml`:
   - `name` must match `SENTRY_PROJECT` (e.g. `shiprocket-web`)
   - `url` = GitHub repo URL

Phoenix will clone the repo, resolve files from Sentry stack trace, fix the bug, validate (npm run build + lint), and open a PR.

---

## Architecture

See **[ARCHITECTURE.md](./ARCHITECTURE.md)** for:

- LangGraph flow (Ingest → Clone → Fix → Validate → PR)
- State schema
- Module breakdown
- POC vs future scope

---

## Directory Structure

```
opus_4.6/
├── config/           # repos.yaml, settings.yaml
├── scripts/          # run_repo_analyzer.py (diagnostic CLI)
├── src/
│   ├── analyzer/    # Repo Analyzer (Angular/Node/coverage scan)
│   ├── orchestrator/ # LangGraph + nodes
│   ├── brain/       # Opus 4.6 client
│   ├── services/    # Repo, GitHub, Validator
│   └── main.py
├── requirements.txt
└── ARCHITECTURE.md
```

---

## Next Steps

1. **Demo repo** – Create a small Angular app with intentional bugs
2. **Implement nodes** – Wire RepoManager, Brain, Validator, GitHubClient
3. **Run POC** – Validate end-to-end flow
4. **Show senior** – Demo: error in → PR out

---

*Brain: Opus 4.6 | Orchestration: LangGraph | Shiprocket FE*
