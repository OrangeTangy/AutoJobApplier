# Implementation Milestones — AutoJobApplier

## Phase 1 — Architecture & Repo Scaffold ✅
**Goal:** Every file exists, Docker stack starts, DB migrates, health endpoint returns 200.

| Task | Status |
|------|--------|
| Planning docs (ARCHITECTURE, THREAT_MODEL, SCHEMA, MILESTONES) | ✅ |
| docker-compose.yml (postgres, redis, backend, worker, frontend) | ✅ |
| FastAPI app skeleton + config + database | ✅ |
| SQLAlchemy models (all tables) | ✅ |
| Alembic initial migration | ✅ |
| Pydantic schemas | ✅ |
| LLM abstraction layer (base + anthropic + mock) | ✅ |
| Auth router (register, login, refresh, logout) | ✅ |
| Stub routers (jobs, resumes, applications, profile, ingestion) | ✅ |
| Next.js 14 app skeleton + Tailwind + shadcn/ui | ✅ |
| .env.example + README | ✅ |

**Exit criteria:** `docker compose up` → DB migrated → `GET /health` → `{"status":"ok"}`

---

## Phase 2 — Data Models & Ingestion Connectors
**Goal:** User can register, log in, create profile, paste a job URL, see it parsed.

| Task | Description |
|------|-------------|
| User auth (register/login/JWT) | Fully working auth flow |
| User profile CRUD | Create/update/read profile |
| Manual URL ingestion | Paste URL → fetch → store raw HTML |
| Email ingestion (Gmail OAuth) | OAuth connect → poll inbox → filter job emails |
| Email ingestion (IMAP) | App password → poll inbox |
| Deduplication service | Hash + upsert |
| Job parser (LLM) | Extract all structured fields |
| Fit scorer (LLM) | Score job vs profile |
| Background polling task | Celery periodic task per source |
| Dashboard API endpoints | Job list with filters |

**Exit criteria:** Paste URL → job appears on dashboard with fit score.

---

## Phase 3 — LaTeX Resume Tailoring Engine
**Goal:** Upload base resume, system generates tailored variant for each job.

| Task | Description |
|------|-------------|
| LaTeX parser | Extract sections, bullets, dates from .tex |
| Resume structured data | Map LaTeX sections → profile schema |
| Tailoring prompt | LLM rewrites bullets for relevance |
| Diff generator | Compare original vs tailored |
| LaTeX compiler | `pdflatex` subprocess in sandbox |
| PDF storage | Store + serve compiled PDF |
| Rationale log | Per-bullet edit reason |
| Resume version history | Track all tailored variants per job |

**Exit criteria:** Upload resume.tex → apply to job → download tailored PDF.

---

## Phase 4 — Job Parser & Question Extractor
**Goal:** Detect all application questions, classify types, ground draft answers.

| Task | Description |
|------|-------------|
| Question type classifier | Pattern + LLM hybrid |
| Questionnaire answer generator | Ground in user profile |
| Confidence scorer | 'high'/'medium'/'low' per answer |
| Sensitive question flagging | Mandatory review for auth/demographic |
| User defaults system | Save approved answers as templates |
| Handshake export parser | Parse CSV/JSON export |
| Saved links importer | Batch URL list |

**Exit criteria:** Job with 10 questions → all questions answered with sources cited.

---

## Phase 5 — Review UI
**Goal:** Full review screen with all application materials visible before approval.

| Task | Description |
|------|-------------|
| Job detail page | Full parsed job summary |
| Fit score breakdown | Visual score + matched/missing skills |
| Resume diff viewer | Side-by-side original vs tailored |
| Questionnaire review table | Question, draft, confidence, source, edit inline |
| Approval button | Single explicit click with confirmation modal |
| Rejection button | Reject with reason |
| Edit & re-draft loop | User edits → re-score → review again |
| Warnings panel | Red flags, missing qualifications |

**Exit criteria:** Review all materials, edit two answers, approve, see status → approved.

---

## Phase 6 — Safe Submission Runner
**Goal:** Approved applications submitted via Playwright with full audit trail.

| Task | Description |
|------|-------------|
| Approval hash validator | Abort if answers changed post-approval |
| Playwright form filler | Map answer types to form field types |
| PDF upload handler | Resume upload via file input |
| Verification pause | Stop and surface challenge to user |
| Submission audit record | Screenshot + result stored |
| Retry with backoff | Network errors only, not auth challenges |
| Submission cooldown | Respect per-company rate limits |
| robots.txt checker | Validate URL before automation |

**Exit criteria:** Approve application → Playwright fills form → user sees submitted status + screenshot.

---

## Phase 7 — Tests, Docs, Deployment
**Goal:** Production-ready with CI, full test coverage, deployment docs.

| Task | Description |
|------|-------------|
| Unit tests: models, utils, services | pytest with fixtures |
| Integration tests: API endpoints | TestClient with real DB |
| E2E tests: UI flows | Playwright test suite |
| CI pipeline | GitHub Actions: lint, test, build, audit |
| Production docker-compose | Nginx, SSL termination, secrets management |
| Performance test | 100 concurrent users, rate limit behavior |
| GDPR purge test | Delete user → verify all data gone |
| Deployment guide | README section: local, staging, production |
| API docs | Auto-generated + annotated with examples |
| Contribution guide | CONTRIBUTING.md |

**Exit criteria:** All tests green, CI passes, deploy guide verified on fresh machine.

---

## Open Issues Tracker

After each phase, new issues discovered are logged here.

| ID | Phase | Description | Priority |
|----|-------|-------------|----------|
| OI-001 | 1 | LaTeX compiler requires texlive installed in Docker; use prebuilt image | High |
| OI-002 | 1 | Playwright browser download adds ~200MB to worker image; use separate Dockerfile.playwright | Medium |
| OI-003 | 1 | Gmail OAuth requires verified app; provide test IMAP path for local dev | Medium |
