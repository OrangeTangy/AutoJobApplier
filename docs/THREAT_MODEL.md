# Threat Model — AutoJobApplier

## Assets

| Asset | Sensitivity | Storage |
|-------|-------------|---------|
| User profile (name, contact, work history) | High | PostgreSQL encrypted columns |
| Resume LaTeX source + compiled PDF | High | Encrypted file storage |
| OAuth tokens (Gmail, LinkedIn) | Critical | AES-256 encrypted, never logged |
| Application questionnaire answers | High | PostgreSQL encrypted columns |
| LLM-generated content | Medium | PostgreSQL |
| Audit logs | Medium | Append-only JSONL |
| Job listings (public) | Low | PostgreSQL |

---

## Threat Actors

| Actor | Motivation | Capability |
|-------|-----------|-----------|
| External attacker | Steal PII, OAuth tokens | Network-level, web exploitation |
| Compromised dependency | Exfiltrate secrets | Supply-chain |
| Malicious job posting | Prompt injection via LLM | Craft job description to hijack LLM output |
| Rogue worker process | Access out-of-scope data | Internal service abuse |
| Platform (job board) | Detect automated access | Bot detection, ToS enforcement |

---

## STRIDE Analysis

### Spoofing
- **Threat:** Attacker impersonates authenticated user to approve/submit applications.
- **Mitigation:** JWT HS256 with short expiry (15 min access / 7 day refresh). HTTPS-only cookies with `SameSite=Strict`. Session invalidation on password change.

### Tampering
- **Threat:** Attacker modifies approved answers between approval and submission.
- **Mitigation:** On approval, SHA-256 hash of all answer fields stored in `applications.approval_hash`. Submission runner recomputes hash and aborts if mismatch.

### Repudiation
- **Threat:** Dispute over what was submitted.
- **Mitigation:** Append-only audit log with `actor_id`, `action`, `payload_hash`, `timestamp`. Application record stores approved snapshot. Cannot be modified post-approval.

### Information Disclosure
- **Threat:** OAuth tokens or resume PII leaked via logs or API responses.
- **Mitigation:**
  - `oauth_tokens` column encrypted at rest (Fernet/AES-256).
  - All API responses scrub token fields.
  - Structured logs explicitly block token fields via `structlog.contextvars`.
  - `/health` endpoint returns status only, no data.

### Denial of Service
- **Threat:** Flood API or trigger unlimited LLM calls.
- **Mitigation:** Per-user rate limits (Redis sliding window) on ingestion and generation endpoints. LLM calls are queued, not inline. Maximum concurrent worker tasks per user configurable.

### Elevation of Privilege
- **Threat:** User A accesses User B's data.
- **Mitigation:** Every DB query scoped by `user_id` foreign key. FastAPI dependency `get_current_user` injected on all protected routes. Row-level validation in service layer (defense in depth).

---

## Prompt Injection Risks

Job descriptions are untrusted external content processed by an LLM.

### Mitigations
1. **Structural separation:** Job description text is placed in a clearly delimited `<job_description>` XML block, never interpolated directly into system prompt.
2. **Schema enforcement:** LLM output parsed as strict Pydantic model; unexpected fields rejected.
3. **Rationale auditing:** Every LLM answer includes a `sources` list referencing user profile fields. Answers that cite no user profile source are flagged for mandatory review.
4. **No code execution from LLM output:** Generated LaTeX is compiled in a sandboxed subprocess with no network access.
5. **User review gate:** All generated content passes through human approval before submission — prompt injection can craft a draft but cannot submit.

---

## Non-Negotiable Safety Controls

These are implemented as hard-coded checks, not configuration:

```python
# submission_runner.py
def _assert_approval_valid(application: Application) -> None:
    """Abort if approval hash does not match current answer state."""
    current_hash = compute_approval_hash(application)
    if current_hash != application.approval_hash:
        raise TamperedApprovalError(application.id)
    if application.status != ApplicationStatus.APPROVED:
        raise NotApprovedError(application.id)
    if application.approved_at is None:
        raise NotApprovedError(application.id)
```

Controls that are **never configurable**:
- Auto-submit without approval
- OTP/MFA/captcha retrieval or bypass
- Fabrication of credentials, GPA, dates, or work history
- Fetching email verification codes automatically
- Scraping sites that disallow it in robots.txt

---

## Data Retention

| Data Type | Default Retention | User Control |
|-----------|-------------------|--------------|
| Job listings | 90 days after rejection | Delete on request |
| Draft applications | 30 days | Delete anytime |
| Approved/submitted applications | 1 year | Delete on request (audit stub kept) |
| Audit logs | 2 years | Cannot delete (compliance) |
| OAuth tokens | Until revoked | Revoke + purge anytime |
| Resume files | Until user deletes | Delete anytime |
| User profile | Until account deletion | Full GDPR-style purge |

---

## Dependency Security

- `pip-audit` runs in CI to scan Python dependencies for known CVEs.
- `npm audit` runs in CI for frontend dependencies.
- Docker images built from pinned digests in production.
- No `eval`, `exec`, or `subprocess.shell=True` with user-controlled input.

---

## Third-Party Integrations

| Integration | Data Shared | Auth Method | Revocable |
|-------------|-------------|-------------|-----------|
| Anthropic API | Job text + user profile excerpt | API key (env var) | Yes — rotate key |
| Gmail | Email headers + body | OAuth2 PKCE | Yes — revoke in Google |
| IMAP | Email headers + body | App password (encrypted) | Yes — purge from settings |
| Job boards (scrape) | None sent | None | N/A |
