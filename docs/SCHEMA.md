# Database Schema — AutoJobApplier

## Conventions
- UUIDs for all primary keys (prevents enumeration attacks)
- `created_at` / `updated_at` on every table (auto-managed by SQLAlchemy events)
- Soft delete via `deleted_at` nullable timestamp; hard purge available via admin API
- Sensitive text columns encrypted with Fernet (symmetric AES-128-CBC + HMAC)
- `JSONB` for semi-structured data (parsed job fields, LLM rationale, diffs)

---

## Entity-Relationship Summary

```
users ──< user_profiles (1:1)
users ──< resumes (1:N)
users ──< jobs (1:N, via job_sources)
jobs ──< applications (1:1 per user per job)
applications ──< questionnaire_answers (1:N)
applications ──< audit_logs (1:N)
users ──< company_rules (1:N)
users ──< ingestion_sources (1:N)
```

---

## Tables

### users
```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,            -- bcrypt
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    is_admin        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);
```

### user_profiles
```sql
CREATE TABLE user_profiles (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    full_name           TEXT NOT NULL,
    phone               TEXT,                          -- encrypted
    location            TEXT,
    linkedin_url        TEXT,
    github_url          TEXT,
    portfolio_url       TEXT,
    work_authorization  TEXT NOT NULL DEFAULT 'unknown',
    -- 'citizen' | 'permanent_resident' | 'opt' | 'cpt' | 'h1b' | 'other' | 'unknown'
    requires_sponsorship BOOLEAN NOT NULL DEFAULT FALSE,
    desired_salary_min  INTEGER,
    desired_salary_max  INTEGER,
    salary_currency     TEXT NOT NULL DEFAULT 'USD',
    earliest_start_date DATE,
    willing_to_relocate BOOLEAN NOT NULL DEFAULT FALSE,
    target_locations    JSONB NOT NULL DEFAULT '[]',   -- ["Remote","New York, NY"]
    education           JSONB NOT NULL DEFAULT '[]',
    -- [{institution, degree, field, gpa, graduated_at, in_progress}]
    work_history        JSONB NOT NULL DEFAULT '[]',
    -- [{company, title, start_date, end_date, bullets: [str]}]
    skills              JSONB NOT NULL DEFAULT '[]',   -- ["Python","TypeScript",...]
    certifications      JSONB NOT NULL DEFAULT '[]',
    custom_qa_defaults  JSONB NOT NULL DEFAULT '{}',
    -- {"why_this_company": "I love...", "biggest_weakness": "..."}
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### resumes
```sql
CREATE TABLE resumes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    is_base         BOOLEAN NOT NULL DEFAULT FALSE,    -- user's canonical resume
    latex_source    TEXT NOT NULL,                     -- encrypted
    compiled_pdf_path TEXT,                            -- path on disk
    parsed_data     JSONB,
    -- {sections: {experience: [...], education: [...], skills: [...], projects: [...]}}
    template_name   TEXT,                              -- 'moderncv' | 'awesome-cv' | etc
    word_count      INTEGER,
    page_count      INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);
```

### ingestion_sources
```sql
CREATE TABLE ingestion_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_type     TEXT NOT NULL,    -- 'gmail' | 'imap' | 'handshake' | 'manual_url'
    display_name    TEXT NOT NULL,
    config          JSONB NOT NULL DEFAULT '{}',       -- encrypted fields inside
    -- gmail: {oauth_token_ref: uuid}
    -- imap: {host, port, username, encrypted_password}
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_polled_at  TIMESTAMPTZ,
    poll_interval_seconds INTEGER NOT NULL DEFAULT 3600,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### jobs
```sql
CREATE TABLE jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_id       UUID REFERENCES ingestion_sources(id),
    dedup_hash      TEXT NOT NULL,   -- SHA256(lower(company)||lower(title)||normalized_url)
    UNIQUE (user_id, dedup_hash),

    -- Raw data
    raw_url         TEXT,
    raw_html        TEXT,            -- stored for audit; scrubbed after parsing
    raw_email_id    TEXT,            -- IMAP/Gmail message ID

    -- Parsed data (LLM extraction)
    title           TEXT,
    company         TEXT,
    location        TEXT,
    remote_policy   TEXT,            -- 'remote' | 'hybrid' | 'onsite' | 'unknown'
    description     TEXT,
    required_skills JSONB NOT NULL DEFAULT '[]',
    preferred_skills JSONB NOT NULL DEFAULT '[]',
    years_experience_min INTEGER,
    years_experience_max INTEGER,
    sponsorship_hint TEXT,           -- 'yes' | 'no' | 'unknown' extracted from text
    salary_min      INTEGER,
    salary_max      INTEGER,
    salary_currency TEXT,
    deadline        DATE,
    application_url TEXT,
    application_questions JSONB NOT NULL DEFAULT '[]',
    -- [{question_text, question_type, required, options}]
    parse_rationale JSONB,           -- LLM reasoning stored for audit

    -- Scoring
    fit_score       SMALLINT,        -- 0-100
    fit_rationale   JSONB,
    -- {matched_skills, missing_skills, red_flags, positive_signals}

    -- Status
    status          TEXT NOT NULL DEFAULT 'new',
    -- 'new' | 'parsing' | 'parsed' | 'scored' | 'draft' | 'review' | 'approved'
    -- | 'submitted' | 'rejected_by_user' | 'rejected_by_employer' | 'error'
    parse_error     TEXT,

    discovered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX idx_jobs_user_status ON jobs(user_id, status);
CREATE INDEX idx_jobs_user_company ON jobs(user_id, company);
CREATE INDEX idx_jobs_fit_score ON jobs(user_id, fit_score DESC);
```

### applications
```sql
CREATE TABLE applications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id          UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    UNIQUE(user_id, job_id),

    resume_id       UUID REFERENCES resumes(id),        -- tailored resume for this job
    cover_letter    TEXT,                                -- encrypted

    -- Approval gate
    status          TEXT NOT NULL DEFAULT 'draft',
    -- 'draft' | 'ready_for_review' | 'approved' | 'rejected' | 'submitted' | 'error'
    approved_at     TIMESTAMPTZ,
    approved_by     UUID REFERENCES users(id),
    approval_hash   TEXT,     -- SHA256 of (resume_id + all answer texts) at approval time

    -- Submission result
    submitted_at    TIMESTAMPTZ,
    submission_url  TEXT,
    submission_screenshot_path TEXT,
    submission_error TEXT,

    -- Feedback loop
    outcome         TEXT,     -- 'no_response' | 'rejected' | 'phone_screen' | 'offer' | ...
    user_notes      TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_applications_user_status ON applications(user_id, status);
```

### questionnaire_answers
```sql
CREATE TABLE questionnaire_answers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id  UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id),

    question_text   TEXT NOT NULL,
    question_type   TEXT NOT NULL,
    -- 'work_authorization' | 'sponsorship' | 'relocation' | 'salary'
    -- | 'start_date' | 'education' | 'years_experience' | 'demographic'
    -- | 'short_answer' | 'yes_no' | 'multiple_choice' | 'unknown'

    draft_answer    TEXT NOT NULL,   -- encrypted; LLM-generated
    final_answer    TEXT,            -- encrypted; user-edited or approved as-is
    confidence      TEXT NOT NULL DEFAULT 'medium',  -- 'high' | 'medium' | 'low'
    requires_review BOOLEAN NOT NULL DEFAULT FALSE,
    sources         JSONB NOT NULL DEFAULT '[]',
    -- ["user_profile.work_authorization", "user_profile.education[0].degree"]
    rationale       TEXT,            -- LLM reasoning
    user_edited     BOOLEAN NOT NULL DEFAULT FALSE,
    approved        BOOLEAN NOT NULL DEFAULT FALSE,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### company_rules
```sql
CREATE TABLE company_rules (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company     TEXT NOT NULL,
    rule_type   TEXT NOT NULL,  -- 'blacklist' | 'allowlist' | 'cooldown'
    reason      TEXT,
    cooldown_days INTEGER,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, company, rule_type)
);
```

### audit_logs
```sql
CREATE TABLE audit_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id),
    actor       TEXT NOT NULL,    -- 'user' | 'worker' | 'system'
    action      TEXT NOT NULL,
    -- 'job_discovered' | 'job_parsed' | 'resume_tailored' | 'answer_generated'
    -- | 'application_approved' | 'application_submitted' | 'answer_edited'
    -- | 'login' | 'token_refreshed' | 'data_purge_requested' | ...
    resource_type TEXT,           -- 'job' | 'application' | 'resume' | 'answer'
    resource_id UUID,
    payload_hash TEXT,            -- SHA256 of sanitized payload (no PII in this field)
    metadata    JSONB NOT NULL DEFAULT '{}',
    -- Non-PII details: model_name, token_count, duration_ms, status_code
    ip_address  INET,
    user_agent  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Append-only: no UPDATE or DELETE permissions granted on this table
CREATE INDEX idx_audit_user_action ON audit_logs(user_id, action, created_at DESC);
```

---

## Encryption Strategy

Columns marked `-- encrypted` use **application-layer Fernet encryption**:
- Key derived from `DATABASE_ENCRYPTION_KEY` env var (32-byte base64)
- Stored as `ENCRYPTED:<base64_ciphertext>` to distinguish from plaintext
- Key rotation: re-encrypt all rows, swap to new key, zero-out old key

```python
# utils/encryption.py
from cryptography.fernet import Fernet

def encrypt(value: str, key: bytes) -> str: ...
def decrypt(value: str, key: bytes) -> str: ...
```

Fields encrypted at rest:
- `user_profiles.phone`
- `resumes.latex_source`
- `applications.cover_letter`
- `questionnaire_answers.draft_answer`
- `questionnaire_answers.final_answer`
- `ingestion_sources.config` (contains passwords/tokens)

---

## Indexes and Performance Notes

- Fit score query: `idx_jobs_fit_score` supports `ORDER BY fit_score DESC LIMIT N`
- Dashboard: `idx_applications_user_status` supports filtered status counts
- Dedup: `UNIQUE(user_id, dedup_hash)` makes upsert O(1)
- Audit queries: `idx_audit_user_action` for compliance exports
