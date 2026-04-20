# AutoJobApplier

A production-grade job application assistant with AI-powered resume tailoring, questionnaire answering, and a mandatory human approval gate before any submission.

> **No auto-submission. No fabricated qualifications. Every answer grounded in your profile. You approve before anything is sent.**

---

## Features

| Feature | Description |
|---------|-------------|
| **Job Ingestion** | Paste a URL, import from Gmail/IMAP, or upload Handshake exports |
| **Deduplication** | Cross-source dedup so each job appears once |
| **Job Parsing** | LLM extracts title, company, skills, sponsorship hints, questions |
| **Fit Scoring** | 0–100 score with matched/missing skills and red flags |
| **Resume Tailoring** | LaTeX resume rewritten for relevance — truthful edits only, with diffs |
| **PDF Compilation** | Tailored resume compiled to PDF via pdflatex |
| **Questionnaire Assistant** | Draft answers for all application questions, grounded in your profile |
| **Sensitive Question Flags** | Work auth, sponsorship, demographic questions flagged for mandatory review |
| **Review UI** | Full review screen: job summary, fit score, resume diff, all answers |
| **Approval Gate** | Single explicit click required before any submission |
| **Submission Runner** | Playwright fills the form — pauses on any verification challenge |
| **Audit Log** | Every action logged with actor, timestamp, and payload hash |
| **Data Purge** | Full GDPR-style user data deletion available |

---

## Architecture

```
Next.js 14  →  FastAPI  →  PostgreSQL
                  ↓
              Redis Queue
                  ↓
           Celery Workers
         (LLM · LaTeX · Playwright)
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full system diagram.

---

## Quick Start (Docker)

### Prerequisites

- Docker & Docker Compose
- An [Anthropic API key](https://console.anthropic.com/)

### 1. Clone and configure

```bash
git clone https://github.com/YOUR_USERNAME/AutoJobApplier.git
cd AutoJobApplier
cp .env.example .env
```

Edit `.env` with your values:

```bash
# Required
DB_PASSWORD=your_strong_db_password
REDIS_PASSWORD=your_strong_redis_password
SECRET_KEY=your_64_char_secret_key          # python -c "import secrets; print(secrets.token_urlsafe(64))"
DATABASE_ENCRYPTION_KEY=your_fernet_key    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 2. Start all services

```bash
docker compose up --build
```

This starts:
- **PostgreSQL** (port 5432)
- **Redis** (port 6379)
- **FastAPI backend** (port 8000) — runs `alembic upgrade head` automatically
- **Celery worker** (ingestion · generation · submission queues)
- **Celery beat** (hourly source polling)
- **Next.js frontend** (port 3000)

### 3. Open the app

[http://localhost:3000](http://localhost:3000)

Register an account → complete your profile → upload your resume → start adding jobs.

---

## Local Development (without Docker)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Set env vars (or copy .env to backend/ and source it)
export DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/autojobapplier"
export REDIS_URL="redis://:password@localhost:6379/0"
export SECRET_KEY="..."
export DATABASE_ENCRYPTION_KEY="..."
export ANTHROPIC_API_KEY="sk-ant-..."

# Migrate
alembic upgrade head

# Run API
uvicorn app.main:app --reload --port 8000

# Run worker (separate terminal)
celery -A app.workers.celery_app worker --loglevel=info
```

### Frontend

```bash
cd frontend
npm install
cp ../.env.example .env.local   # edit NEXT_PUBLIC_API_URL etc.
npm run dev
```

### Run tests

```bash
cd backend
pytest --cov=app tests/
```

---

## API Documentation

With the backend running, visit:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Key endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/auth/register` | Create account |
| `POST` | `/api/v1/auth/login` | Get tokens |
| `GET` | `/api/v1/profile` | Get user profile |
| `PUT` | `/api/v1/profile` | Update profile |
| `POST` | `/api/v1/jobs/ingest` | Add job URL |
| `GET` | `/api/v1/jobs` | List jobs (with filters) |
| `POST` | `/api/v1/resumes` | Upload LaTeX resume |
| `POST` | `/api/v1/resumes/tailor` | Start tailoring for a job |
| `POST` | `/api/v1/applications/{job_id}/draft` | Create draft application |
| `POST` | `/api/v1/applications/{id}/approve` | **Approve application** (required before submission) |
| `POST` | `/api/v1/applications/{id}/submit` | Submit approved application |
| `GET` | `/health` | Service health check |

---

## Workflow

```
1. Add your profile (work auth, skills, education, salary expectations)
2. Upload your base LaTeX resume
3. Paste a job URL → system parses + scores fit
4. Click "Start Application" → system generates tailored resume + answers
5. Review every answer in the UI — edit anything you want
6. Click "Approve" (single explicit action)
7. Click "Submit" → Playwright fills the form
   → Pauses automatically if any verification challenge appears
8. Log the outcome (interview, rejection, offer)
```

---

## Safety & Compliance

| Rule | Enforcement |
|------|-------------|
| No auto-submit | Hard-coded approval check in `submission_runner.py` — cannot be bypassed by config |
| No fabrication | LLM system prompt + answer sources always cite profile fields |
| No OTP/captcha bypass | Challenge detection immediately pauses and surfaces to user |
| Approval integrity | SHA-256 hash of all answers computed at approval; recomputed before submission — mismatch aborts |
| Audit log | Every action logged — immutable append-only table |
| Encryption | Sensitive fields (resume LaTeX, phone, answers, OAuth tokens) encrypted at rest with Fernet |

---

## Project Structure

```
AutoJobApplier/
├── docs/
│   ├── ARCHITECTURE.md        System design and data flow
│   ├── THREAT_MODEL.md        STRIDE analysis and mitigations
│   ├── SCHEMA.md              Full database schema
│   └── MILESTONES.md          Phase-by-phase implementation plan
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI app + middleware
│   │   ├── config.py          Pydantic settings
│   │   ├── database.py        Async SQLAlchemy engine
│   │   ├── models/            SQLAlchemy ORM models
│   │   ├── schemas/           Pydantic request/response schemas
│   │   ├── routers/           FastAPI route handlers
│   │   ├── services/
│   │   │   ├── llm/           LLM abstraction layer (Anthropic + Mock)
│   │   │   ├── job_parser.py  URL fetch + LLM job extraction
│   │   │   ├── fit_scorer.py  Profile vs. job fit scoring
│   │   │   ├── resume_tailor.py  LaTeX tailoring + PDF compile
│   │   │   ├── questionnaire.py  Answer generation
│   │   │   └── submission_runner.py  Playwright submission (approval-gated)
│   │   ├── workers/           Celery app + scheduled tasks
│   │   └── utils/
│   │       ├── audit.py       Audit log writer
│   │       ├── encryption.py  Fernet encrypt/decrypt
│   │       ├── latex.py       LaTeX resume parser
│   │       └── security.py    JWT, bcrypt, approval hash
│   ├── alembic/               Database migrations
│   └── tests/                 pytest test suite
├── frontend/
│   └── src/
│       ├── app/               Next.js App Router pages
│       ├── components/        Reusable UI components
│       ├── lib/               API client, utilities
│       └── types/             TypeScript interfaces
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Implementation Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1 — Scaffold | ✅ | Architecture docs, repo structure, Docker, DB migrations, basic API |
| 2 — Ingestion | 🔜 | Gmail OAuth, IMAP polling, Handshake export, dedup |
| 3 — LaTeX Engine | 🔜 | Full parser, tailoring, PDF compilation, diff viewer |
| 4 — Questions | 🔜 | All question types, grounded answers, confidence scoring |
| 5 — Review UI | 🔜 | Full review screen, inline editing, resume diff |
| 6 — Submission | 🔜 | Site-specific Playwright adapters, verification pause |
| 7 — Tests & Deploy | 🔜 | Full test coverage, CI, production deployment guide |

---

## Environment Variables

See [`.env.example`](.env.example) for all variables with descriptions.

**Required to start:**
- `DB_PASSWORD`
- `REDIS_PASSWORD`
- `SECRET_KEY` (64+ random characters)
- `DATABASE_ENCRYPTION_KEY` (Fernet key)
- `ANTHROPIC_API_KEY` (or leave blank to use Mock LLM for testing)

---

## Contributing

See [`docs/MILESTONES.md`](docs/MILESTONES.md) for the open issues list and next steps.

1. Fork the repo
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Run tests: `cd backend && pytest`
4. Submit a PR

---

## License

MIT
