# System Architecture — AutoJobApplier

## Overview

AutoJobApplier is a production-grade job application assistant that helps users discover
relevant opportunities, tailor application materials, prepare questionnaire answers, and
queue applications for explicit human approval before any submission occurs.

---

## Guiding Principles

| Principle | Implementation |
|-----------|---------------|
| Safety first | No submission without per-application user approval |
| Truthfulness | Every generated answer grounded in user profile |
| Compliance | Robots.txt, ToS, rate limits respected |
| Auditability | Every action logged with actor, timestamp, payload hash |
| Privacy | Minimal data, encryption at rest, purge-on-demand |

---

## High-Level Component Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                           User Browser                               │
│                    Next.js 14 + TypeScript UI                        │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTPS / REST + SSE
┌────────────────────────────▼────────────────────────────────────────┐
│                    FastAPI Backend  :8000                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │  /auth   │ │  /jobs   │ │/resumes  │ │  /apps   │ │ /profile │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ │
│       └────────────┴────────────┴─────────────┴────────────┘        │
│                          Service Layer                                │
│  ┌────────────┐ ┌──────────────┐ ┌────────────────┐ ┌────────────┐ │
│  │ JobParser  │ │ ResumeTailor │ │ Questionnaire  │ │ Submission │ │
│  │            │ │ + LaTeXPipe  │ │ Assistant      │ │ Runner     │ │
│  └────────────┘ └──────────────┘ └────────────────┘ └────────────┘ │
│                          LLM Abstraction Layer                        │
│           ┌─────────────────┬─────────────────┐                     │
│           │  Anthropic SDK  │  Mock (testing) │                     │
│           └─────────────────┴─────────────────┘                     │
└───────────┬──────────────────────────┬──────────────────────────────┘
            │                          │
┌───────────▼──────────┐  ┌───────────▼──────────────────────────────┐
│   PostgreSQL :5432   │  │         Redis :6379                       │
│   (primary store)    │  │  ┌──────────────┐  ┌────────────────────┐ │
│                      │  │  │  Task Queue  │  │  Rate-limit store  │ │
│   Encrypted fields:  │  │  │  (Celery)    │  │  Session cache     │ │
│   - oauth_tokens     │  │  └──────────────┘  └────────────────────┘ │
│   - email_creds      │  └──────────────────────────────────────────┘
│   - answers          │
└──────────────────────┘
            │
┌───────────▼──────────────────────────────────────────────────────────┐
│                         Celery Worker                                  │
│  ┌───────────────┐  ┌────────────────┐  ┌──────────────────────────┐ │
│  │ poll_sources  │  │ prepare_draft  │  │  submission_runner       │ │
│  │ (email/feeds) │  │ (LLM pipeline) │  │  (Playwright — approved  │ │
│  └───────────────┘  └────────────────┘  │   jobs only)             │ │
│                                          └──────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
            │
┌───────────▼──────────────────────────────────────────────────────────┐
│                     File Storage (local / S3-compatible)               │
│   /resumes/{user_id}/{resume_id}.tex   (LaTeX source)                 │
│   /resumes/{user_id}/{resume_id}.pdf   (compiled output)              │
│   /audit/{date}/{action_id}.jsonl      (append-only audit log)        │
└───────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack Decision Log

### Backend: FastAPI (Python 3.11+)
**Why not Node.js:** The pipeline is CPU- and I/O-heavy (LaTeX compilation, LLM calls,
PDF diffs). Python's ecosystem (anthropic SDK, playwright-python, pypdf, latexcodec,
sqlalchemy async) is superior here. FastAPI provides async support, OpenAPI docs,
and Pydantic validation out of the box.

### Queue: Celery + Redis
**Why not BullMQ:** Backend is Python; Celery integrates natively. Redis doubles as
session cache and rate-limit store, reducing infra complexity.

### ORM: SQLAlchemy 2.0 async + Alembic
Full async support, type-safe query API, migration history.

### Frontend: Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui
SSR for fast initial load on the review screen; React Query for real-time status
polling; Zustand for approval state.

### Browser automation: Playwright (Python)
Only invoked after explicit per-application user approval. Never used for auth bypass.

---

## Data Flow: Job Discovery → Submission

```
1. INGESTION
   Email / URL paste / file import
         │
         ▼
2. DEDUPLICATION
   Hash(company + title + url) checked against jobs table
         │
         ▼
3. JOB PARSING  (LLM)
   Extract: title, company, location, skills, deadline,
            sponsorship hints, YoE, application questions
         │
         ▼
4. FIT SCORING  (LLM)
   Compare job requirements ↔ user profile
   Output: score 0-100, missing quals, red flags
         │
         ▼
5. RESUME TAILORING  (LLM + LaTeX pipeline)
   Clone base resume LaTeX
   Reorder / emphasize bullets for relevance
   Compile PDF
   Store diff + rationale
         │
         ▼
6. QUESTIONNAIRE DRAFTING  (LLM)
   Pattern-match questions → types
   Ground answers in user profile
   Flag sensitive questions for mandatory review
         │
         ▼
7. HUMAN REVIEW  (UI — BLOCKING GATE)
   ┌──────────────────────────────────────────┐
   │  Job summary + fit score                  │
   │  Resume diff (original vs tailored)       │
   │  All questionnaire draft answers          │
   │  Warnings (missing quals, red flags)      │
   │  [ APPROVE ]   [ REJECT ]   [ EDIT ]     │
   └──────────────────────────────────────────┘
         │  (explicit click required)
         ▼
8. SUBMISSION  (Playwright)
   Navigate to application URL
   Fill form fields using approved answers only
   Upload approved tailored resume PDF
   Pause on any unexpected verification challenge
   Record result in audit log
```

---

## LLM Abstraction Layer

```python
class LLMProvider(ABC):
    async def complete(self, prompt: str, system: str, **kwargs) -> LLMResponse: ...
    async def complete_structured(self, prompt, system, output_schema, **kwargs): ...

class AnthropicProvider(LLMProvider): ...   # production
class MockProvider(LLMProvider): ...        # tests / CI
```

All LLM calls include:
- Model name in audit log
- Input token count
- Rationale field in structured output
- Grounding citations back to user profile fields

---

## Security Boundaries

```
INGESTION  ─────────────────────────────────────────────────────────
  Can: read email (OAuth scoped), fetch permitted URLs
  Cannot: write to jobs table without validation, submit anything

GENERATION  ────────────────────────────────────────────────────────
  Can: read user profile, read approved resumes, call LLM
  Cannot: modify user profile, trigger submissions, access OAuth tokens

REVIEW  ────────────────────────────────────────────────────────────
  Can: read all draft data, write approval/rejection decision
  Cannot: modify submitted applications, access submission credentials

SUBMISSION  ────────────────────────────────────────────────────────
  Can: read approved application data, drive browser
  Cannot: proceed without approval record, bypass verification challenges
  Cannot: read email/OAuth tokens directly (passed via encrypted ref)
```

---

## Observability

- **Structured logging**: JSON via `structlog`, written to stdout + file
- **Audit log**: Append-only JSONL per day in `/storage/audit/`
- **Metrics**: Prometheus counters on jobs discovered, drafts prepared, submissions attempted/succeeded/failed
- **Error tracking**: Sentry SDK (optional, configured via `SENTRY_DSN` env var)
- **Health endpoint**: `GET /health` returns service + DB + Redis + worker status
