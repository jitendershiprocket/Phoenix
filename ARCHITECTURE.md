# Project Phoenix — Architecture Design

> **Self-Healing Autonomous AI Agent** for Shiprocket Frontend Engineering  
> POC-first, then scalable to 7+ repos

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           PROJECT PHOENIX                                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌─────────────┐    ┌──────────────────────────────────────────────────────┐   │
│   │  TRIGGERS   │    │              ORCHESTRATOR (LangGraph)                 │   │
│   │             │───▶│                                                       │   │
│   │ • Sentry    │    │   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌────────┐  │   │
│   │ • Datadog   │    │   │ Analyze │─▶│ Fix     │─▶│ Validate│─▶│ PR     │  │   │
│   │ • Manual   │    │   │ Node    │  │ Node    │  │ Node    │  │ Node   │  │   │
│   └─────────────┘    │   └─────────┘  └─────────┘  └─────────┘  └────────┘  │   │
│                      │         │            │            │            │       │   │
│                      │         ▼            ▼            ▼            ▼       │   │
│                      │   ┌─────────────────────────────────────────────────┐ │   │
│                      │   │              STATE (Shared Context)              │ │   │
│                      │   │  error_info, repo_path, fix_attempts, pr_url    │ │   │
│                      │   └─────────────────────────────────────────────────┘ │   │
│                      └──────────────────────────────────────────────────────┘   │
│                                           │                                      │
│   ┌─────────────┐    ┌────────────────────┴────────────────────┐                │
│   │   BRAIN     │    │              TOOLS / SERVICES            │                │
│   │             │◀───│                                           │                │
│   │ Opus 4.6   │    │  GitHub API │ Sentry API │ Docker │ ng test │ ng lint    │
│   └─────────────┘    └──────────────────────────────────────────┘                │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. LangGraph Flow (Agentic Loop)

```
                    ┌─────────────────────────────────────┐
                    │           START                     │
                    │  (error / tech-debt input)          │
                    └─────────────────┬───────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  NODE 1: INGEST & ANALYZE                                                         │
│  • Parse error (Sentry/Datadog payload or manual)                                  │
│  • Identify repo, file, stack trace                                                │
│  • Fetch repo metadata (Angular version, Node version)                             │
│  • Exit: → FIX                                                                     │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  NODE 2: REPO CLONE / CHECKOUT                                                    │
│  • Clone repo (or use cached workspace)                                            │
│  • Checkout target branch                                                          │
│  • Create fix branch                                                               │
│  • Exit: → FIX                                                                     │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  NODE 3: FIX (AI)                                                                 │
│  • Build context: error + file content + surrounding code                          │
│  • Call Opus 4.6 with structured prompt                                            │
│  • Parse AI response → apply code edits                                            │
│  • Exit: → VALIDATE                                                                │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  NODE 4: VALIDATE                                                                 │
│  • Run: ng test (or npm test)                                                      │
│  • Run: ng lint (or npm run lint)                                                  │
│  • If PASS → PR                                                                    │
│  • If FAIL → increment attempt, max 3 → back to FIX or ABORT                       │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │                                   │
                    ▼                                   ▼
┌───────────────────────────────┐     ┌─────────────────────────────────┐
│  NODE 5a: CREATE PR           │     │  NODE 5b: ABORT / REPORT        │
│  • Commit changes             │     │  • Log failure                  │
│  • Push branch                │     │  • Store diagnostics            │
│  • Create PR via GitHub API   │     │  • (Optional: notify)           │
│  • Attach RCA in description  │     │  • END                          │
│  • END                        │     └─────────────────────────────────┘
└───────────────────────────────┘
```

---

## 3. Module Breakdown

| Module | Purpose | Tech |
|--------|---------|------|
| **Orchestrator** | LangGraph state machine, node wiring | Python, LangGraph |
| **Brain** | LLM calls for analysis + code fix | Anthropic API (Opus 4.6) |
| **Repo Manager** | Clone, checkout, branch, commit, push | GitPython, GitHub API |
| **Validator** | ng test, ng lint in Docker | Docker, subprocess |
| **PR Service** | Create PR, RCA body | GitHub API |
| **Ingest** | Parse Sentry/Datadog / manual input | Python |
| **Config** | Repos, env vars, model settings | YAML / .env |
| **Analyzer** | Scan repos for Angular/Node/coverage | Python, PyGithub |

---

### LangGraph Node Organization

| Node | Responsibility | Depends On |
|------|----------------|------------|
| **ingest** | Parse error, resolve repo → file, fetch metadata via Analyzer | RepoAnalyzer, ingest_parser |
| **clone** | Clone repo, checkout branch, create fix branch | repo_manager |
| **fix** | Build context, call Opus 4.6, apply edits | brain client |
| **validate** | Run ng test + ng lint (Docker or local) | validator |
| **pr** | Commit, push, create PR with RCA | github_client |

The **Analyzer** module runs in two modes:
1. **Standalone CLI** — `python scripts/run_repo_analyzer.py` to scan all 7 repos.
2. **Ingest integration** — When error arrives without angular/node metadata, Ingest calls Analyzer to fetch it.

---

## 4. Directory Structure

```
opus_4.6/
├── config/
│   ├── repos.yaml              # Repo list (7 Shiprocket repos)
│   └── settings.yaml           # Model, limits, paths
│
├── scripts/
│   └── run_repo_analyzer.py    # CLI: scan repos for Angular/Node/coverage
│
├── src/
│   ├── __init__.py
│   ├── main.py                 # Entry: python -m src.main
│   │
│   ├── analyzer/               # Repository Analyzer & Diagnostic Module
│   │   ├── __init__.py
│   │   └── repo_analyzer.py    # GitHub API scan: Angular, Node, coverage config
│   │
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── graph.py            # LangGraph definition
│   │   ├── state.py            # Shared state schema
│   │   └── nodes/
│   │       ├── ingest.py       # Ingest & Analyze (uses analyzer)
│   │       ├── clone.py        # Repo clone node
│   │       ├── fix.py          # AI Fix node
│   │       ├── validate.py     # Test + Lint node
│   │       └── pr.py           # Create PR node
│   │
│   ├── brain/
│   │   ├── __init__.py
│   │   ├── client.py           # Opus 4.6 API client
│   │   └── prompts.py          # System + user prompts
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── repo_manager.py     # Clone, checkout, commit
│   │   ├── github_client.py    # GitHub API
│   │   ├── validator.py        # Docker + ng test/lint
│   │   └── ingest_parser.py    # Sentry/Datadog parser
│   │
│   └── utils/
│       ├── __init__.py
│       └── logging.py
│
├── .env.example
├── requirements.txt
├── Dockerfile                  # Sandbox for ng test/lint
├── ARCHITECTURE.md
└── README.md
```

---

## 5. State Schema (LangGraph)

```python
from typing import TypedDict, Optional

class PhoenixState(TypedDict):
    # Input
    error_payload: dict           # Raw Sentry/Datadog or manual
    repo_url: str
    branch: str

    # After Ingest
    error_summary: str
    file_path: str
    stack_trace: str
    angular_version: Optional[str]
    node_version: Optional[str]

    # After Clone
    repo_path: str
    fix_branch: str

    # After Fix
    fix_applied: bool
    fix_attempt: int
    max_attempts: int

    # After Validate
    tests_passed: bool
    lint_passed: bool
    validation_log: str

    # After PR
    pr_url: Optional[str]
    status: str                   # "success" | "failed" | "aborted"
```

---

## 6. POC Scope vs Future

| Aspect | POC (Now) | Future |
|--------|-----------|--------|
| Repos | 1 demo repo | 7 production repos |
| Trigger | Manual (CLI input) | Sentry webhook, Datadog |
| Docker | Optional (local ng test) | Mandatory sandbox |
| RCA | Simple summary | Full RCA with recommendations |
| Migrations | Basic fixes only | AngularJS → Angular, Signals |

---

## 7. Run Command (POC)

```bash
# From opus_4.6 directory
python -m src.main --repo https://github.com/org/demo-angular-app \
  --error "TypeError: Cannot read property 'id' of undefined at UserService.getUser (user.service.ts:42)"

# With Sentry event ID (future)
python -m src.main --sentry-event abc123
```

---

## 8. Tech Stack Summary

| Layer | Technology |
|-------|------------|
| Brain | Opus 4.6 (`claude-opus-4-6`) |
| Orchestration | LangGraph |
| Language | Python 3.11+ |
| Repo / PR | GitHub API, GitPython |
| Validation | Docker, Angular CLI |
| Config | YAML, .env |

---

*Document Version: 1.0 | Project Phoenix POC*
