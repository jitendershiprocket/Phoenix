# Project Phoenix — Technical Overview & FAQ

> Agent ka architecture, capabilities, aur commonly puche jane wale questions.

---

## 1. Phoenix Kya Hai?

**Phoenix** ek **self-healing AI agent** hai jo:
1. Sentry se bug fetch karta hai (ya manual error input leta hai)
2. Repo clone karta hai
3. Sahi file dhundhkar fix apply karta hai
4. `ng build` + lint se validate karta hai
5. Success pe GitHub PR create karta hai

---

## 2. High-Level Architecture

```
┌─────────────┐     ┌──────────────────────────────────────────────────────────┐
│  TRIGGERS   │     │              LangGraph Orchestrator                      │
│  • Sentry   │────▶│  INGEST → CLONE → FIX (AI) → VALIDATE → PR / RETRY       │
│  • Manual   │     │     │         │       │           │         │             │
└─────────────┘     │     ▼         ▼       ▼           ▼         ▼             │
                    │  error    repo    Opus 4.6    build+    commit+           │
                    │  parse    clone   fix code    lint      push PR           │
                    └──────────────────────────────────────────────────────────┘
```

**Flow:** Ingest → Clone → Fix → Validate → (PR | Retry Fix | Abort)

---

## 3. Kya-Kya Handle Karta Hai?

### 3.1 File Resolution (Sabse Critical)

Sentry minified bundles se aata hai — file path often `:?` ya `main`. Phoenix **culprit** aur **stack trace** se file resolve karta hai.

| Strategy | Example |
|----------|---------|
| **Direct path** | Sentry se `src/app/services/user.service.ts` mila → direct use |
| **Filename from stack** | Stack me `user.service.ts:42` → repo me search |
| **Content search** | Culprit `_CacheService.get(main)` → tokens extract → repo scan |

**Scoring (same-name files):**
- **Definition-site bonus (15):** `CacheService.get` → file jisme `class CacheService` + `get(` dono hon
- **Type-to-filename (10):** `CacheService` → `cache.service.ts` prefer
- **Error property (5):** "reading 'value'" → file me `.value` access
- **Path priority:** `src/app/` > `app/` > `lib/`
- **Minified handling:** `_CacheService` → `CacheService` token add

**Supported file types:** services, components, pipes, directives, guards, utils, lib — koi bhi `.ts`/`.tsx`/`.js`/`.jsx`/`.py`

### 3.2 Validation

- **Build:** `npm run build` (ng build) — TS/compile errors pakadta hai
- **Lint:** Default **sirf changed file** pe `eslint` (production me full lint nahi chalata)
- **Config:** `lint_changed_only: true` in settings.yaml

### 3.3 Retry Logic

- Max **3 fix attempts**
- Validate fail → dubara Fix node → naya AI fix
- 3 ke baad bhi fail → **Abort** (PR nahi banega)

### 3.4 Multi-Repo Support

- `config/repos.yaml`: `name` = Sentry project slug, `url` = GitHub repo
- `SENTRY_REPO_URL` in .env for single-repo
- SENTRY_PROJECT name se repo map hota hai

---

## 4. Tech Stack

| Component | Tech |
|-----------|------|
| **Orchestration** | LangGraph (Python) |
| **AI / Brain** | Anthropic Opus 4.6 (Claude) |
| **Sentry** | Sentry REST API |
| **Git** | GitPython + GitHub API |
| **Validation** | npm, ng build, eslint |
| **Config** | YAML + .env |

---

## 5. Important Paths

```
phoenix/
├── src/
│   ├── main.py              # Entry: --from-sentry, --repo, --error
│   ├── orchestrator/
│   │   ├── graph.py         # LangGraph flow
│   │   ├── state.py         # Shared state schema
│   │   └── nodes/
│   │       ├── ingest.py    # Parse error, fetch metadata
│   │       ├── clone.py     # Clone repo, create fix branch
│   │       ├── fix.py       # File resolve + AI fix (core)
│   │       ├── validate.py  # Build + lint
│   │       └── pr.py        # Commit, push, create PR
│   ├── brain/
│   │   ├── client.py        # Opus 4.6 API
│   │   └── prompts.py       # Fix prompts
│   └── services/
│       ├── sentry_client.py # Sentry API
│       ├── validator.py     # ng build, eslint
│       └── repo_manager.py  # Git operations
├── config/
│   ├── repos.yaml           # Sentry → Repo mapping
│   └── settings.yaml        # Model, validation, paths
└── workspace/               # Cloned repos
```

---

## 6. Potential Q&A

### Q1: Sentry se file path nahi mila (minified) — Phoenix kaise fix karega?

**A:** Culprit se tokens nikalte hain (e.g. `_CacheService.get` → `CacheService`, `get`). Repo me content search karke jitni files match karti hain unhe score karte hain. Definition-site (class + method wali file) ko highest score dete hain. Minified names ke liye leading underscore hata kar extra token add karte hain.

### Q2: Multiple files same name (e.g. 2 jagah `cache.service.ts`) — kaunsa fix hoga?

**A:** Path priority + definition bonus + type bonus se best file select hoti hai. `src/app/services/cache.service.ts` ko `admin/cache.service.ts` se prefer karte hain. Agar culprit `CacheService.get` hai to woh file choose hogi jisme `class CacheService` aur `get(` dono hon.

### Q3: Bug service me hai ya component me — kaise pata chalega?

**A:** Prompts me koi hardcoded assumption nahi. File resolution generic hai — culprit tokens (e.g. `DashboardComponent.ngOnInit`) se `dashboard.component.ts` mil jati hai. Service, component, pipe, util, guard — sab handle hote hain.

### Q4: Production me full project pe lint nahi chalana — kya karein?

**A:** `config/settings.yaml` me `lint_changed_only: true` (default) set hai. Sirf jis file me fix lagaya usi pe `eslint` chalega. Pura project lint nahi hota.

### Q5: Fix galat file me laga diya — kyu?

**A:** Possible reasons: (1) Culprit ambiguous tha — multiple files same tokens match karti thi, (2) Definition-site bonus sahi file ko nahi mila (e.g. call-site vs definition-site), (3) Minified name (`_Xxx`) properly normalize nahi hua. Solution: File resolution logic improve karo (scoring tweak, extra signals).

### Q6: AI ne galat fix diya (wrong code change) — kya hota hai?

**A:** Validate step (`ng build` / lint) fail hoga. Phoenix retry karega (max 3). Har attempt me naya prompt + same context jata hai. 3 ke baad abort, PR nahi banega.

### Q7: Kitne repos support hain?

**A:** `repos.yaml` me jitne add karoge utne. SENTRY_PROJECT name se match hota hai. Single repo ke liye `SENTRY_REPO_URL` env variable bhi use ho sakta hai.

### Q8: Unit tests chalte hain kya?

**A:** Nahi. Sirf `ng build` + lint. Build me TS errors pakad jaati hain. Unit tests optional (POC me disabled).

### Q9: Node version ka conflict ho to?

**A:** `settings.yaml` me `node_version: "18"` set hai. NVM use karke validation se pehle `nvm use 18` chalta hai.

### Q10: Manual mode me kaise chalana hai?

**A:**
```bash
python -m src.main --repo https://github.com/org/repo \
  --error "TypeError: Cannot read properties of undefined (reading 'id')"
```
`--from-sentry` ke bina Sentry fetch nahi hoga, error input se use hoga.

### Q11: Sentry integration ke liye kya env variables chahiye?

**A:** `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT`. Repo ke liye `SENTRY_REPO_URL` ya `repos.yaml`.

### Q12: Fix prompt me kya constraints hain?

**A:** (1) Sirf reported error fix karo, baaki code mat chhedo, (2) Minimal change (1–3 lines), (3) File ka full content return karo markdown code block me, (4) Optional chaining / try-catch jaisa language-appropriate fix use karo.

### Q13: Workspace me clone kahan hota hai?

**A:** `phoenix/workspace/<repo-name>/` — e.g. `workspace/demo-app/`. `cache_repos: true` pe same branch pe fetch/checkout reuse hota hai.

### Q14: PR description me kya likha hota hai?

**A:** Error summary, file path, fix description — PR node me set hota hai.

### Q15: Phoenix fail ho jaye (abort) — kya output milta hai?

**A:** Status `aborted`, `fix_applied` true/false, `validation_log` (build/lint error). PR nahi banega.

---

## 7. Summary — One-Liner Answers

| Question | Answer |
|----------|--------|
| Phoenix kya karta hai? | Sentry bug → clone → AI fix → validate → PR |
| Kaun sa AI? | Anthropic Opus 4.6 |
| File kaise resolve hoti hai? | Culprit + stack → tokens → content search + scoring |
| Minified code? | `_Xxx` → `Xxx` normalize, definition-site prefer |
| Lint full project? | Nahi, sirf changed file (config se) |
| Retry? | Haan, max 3 attempts |
| Multi-repo? | Haan, repos.yaml |
| Unit tests? | Nahi, sirf build + lint |

---

*Document for Project Phoenix — Technical Demo & FAQ*
