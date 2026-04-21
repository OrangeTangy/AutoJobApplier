"""
Email ingestion service.

Fetches job-related emails from IMAP or Gmail and creates Job records.
- Does NOT auto-retrieve OTP, verification codes, or MFA codes.
- Only reads emails; never sends or deletes.
- Uses user-authorized OAuth/app-password credentials only.
"""
from __future__ import annotations

import email
import hashlib
import re
import uuid
from datetime import datetime, timezone
from email.header import decode_header

import structlog

logger = structlog.get_logger(__name__)

# Keywords that suggest a job-related email
JOB_KEYWORDS = re.compile(
    r"\b(job|position|role|opportunity|hiring|recruiter|application|interview"
    r"|career|opening|vacancy|talent|offer|candidate)\b",
    re.IGNORECASE,
)

# Phrases that mean it's a verification/OTP email — SKIP THESE
SKIP_PATTERNS = re.compile(
    r"\b(verification code|one.?time password|otp|confirm your email"
    r"|security code|login code|authenticate|2fa|two.factor)\b",
    re.IGNORECASE,
)


def decode_mime_header(value: str) -> str:
    parts = decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _extract_text_from_message(msg: email.message.Message) -> str:
    """Extract plain text from a MIME email message."""
    text_parts = []
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                if payload:
                    text_parts.append(payload.decode(charset, errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        if payload:
            text_parts.append(payload.decode(charset, errors="replace"))
    return "\n".join(text_parts)


def _is_job_email(subject: str, body: str) -> bool:
    combined = f"{subject} {body[:500]}"
    if SKIP_PATTERNS.search(combined):
        return False
    return bool(JOB_KEYWORDS.search(combined))


def _email_dedup_hash(user_id: str, message_id: str, subject: str) -> str:
    key = f"{user_id}|{message_id}|{subject.lower().strip()}"
    return hashlib.sha256(key.encode()).hexdigest()


# ── IMAP ──────────────────────────────────────────────────────────────────────

async def poll_imap(
    source_id: uuid.UUID,
    user_id: uuid.UUID,
    host: str,
    port: int,
    username: str,
    password: str,
    folder: str = "INBOX",
    max_messages: int = 50,
) -> list[dict]:
    """
    Connect to IMAP, fetch unseen messages, filter for job emails.
    Returns list of raw job data dicts ready to be inserted as Job records.
    Does NOT retrieve OTP or verification codes.
    """
    try:
        import imapclient
    except ImportError:
        logger.error("imapclient_not_installed")
        return []

    results = []
    try:
        with imapclient.IMAPClient(host, port=port, ssl=True) as client:
            client.login(username, password)
            client.select_folder(folder, readonly=True)

            # Fetch only UNSEEN messages, up to max_messages
            message_ids = client.search(["UNSEEN"])
            if not message_ids:
                logger.info("imap_no_new_messages", source_id=str(source_id))
                return []

            # Process most recent first
            to_fetch = list(reversed(message_ids))[:max_messages]
            fetched = client.fetch(to_fetch, ["RFC822", "ENVELOPE"])

            for uid, data in fetched.items():
                raw = data.get(b"RFC822", b"")
                if not raw:
                    continue

                msg = email.message_from_bytes(raw)
                subject = decode_mime_header(msg.get("Subject", ""))
                from_addr = decode_mime_header(msg.get("From", ""))
                message_id = msg.get("Message-ID", str(uid))
                body = _extract_text_from_message(msg)

                if not _is_job_email(subject, body):
                    continue

                dedup_hash = _email_dedup_hash(str(user_id), message_id, subject)
                results.append({
                    "user_id": user_id,
                    "source_id": source_id,
                    "dedup_hash": dedup_hash,
                    "raw_email_id": message_id,
                    "raw_url": None,
                    "raw_html": None,
                    "title": subject,
                    "company": _extract_company_from_address(from_addr),
                    "description": body[:10000],
                    "status": "parsed",
                    "discovered_at": datetime.now(timezone.utc),
                })

            logger.info(
                "imap_poll_complete",
                source_id=str(source_id),
                fetched=len(to_fetch),
                job_emails=len(results),
            )
    except Exception as exc:
        logger.error("imap_poll_failed", source_id=str(source_id), error=str(exc))

    return results


def _extract_company_from_address(from_addr: str) -> str:
    """Best-effort company extraction from email From header."""
    match = re.search(r'"?([^"<@]+)"?\s*<', from_addr)
    if match:
        name = match.group(1).strip()
        if len(name) > 2:
            return name
    # Fall back to domain
    domain_match = re.search(r"@([\w.-]+)", from_addr)
    if domain_match:
        parts = domain_match.group(1).split(".")
        return parts[-2].title() if len(parts) >= 2 else domain_match.group(1)
    return ""


# ── Gmail ─────────────────────────────────────────────────────────────────────

async def poll_gmail(
    source_id: uuid.UUID,
    user_id: uuid.UUID,
    oauth_token: str,
    max_messages: int = 50,
) -> list[dict]:
    """
    Poll Gmail via API using an OAuth access token.
    Only reads messages; does NOT retrieve OTP codes.
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        logger.error("google_api_not_installed")
        return []

    results = []
    try:
        creds = Credentials(token=oauth_token)
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)

        # Search for job-related emails, not read
        query = (
            "is:unread "
            "(subject:job OR subject:opportunity OR subject:hiring OR subject:interview "
            "OR subject:application OR subject:recruiter OR subject:career) "
            "-subject:verification -subject:OTP -subject:\"one-time\""
        )

        resp = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_messages)
            .execute()
        )
        messages = resp.get("messages", [])

        for msg_ref in messages:
            msg_id = msg_ref["id"]
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )

            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            subject = headers.get("Subject", "")
            from_addr = headers.get("From", "")

            body = _extract_gmail_body(msg)
            if not _is_job_email(subject, body):
                continue

            dedup_hash = _email_dedup_hash(str(user_id), msg_id, subject)
            results.append({
                "user_id": user_id,
                "source_id": source_id,
                "dedup_hash": dedup_hash,
                "raw_email_id": msg_id,
                "raw_url": None,
                "raw_html": None,
                "title": subject,
                "company": _extract_company_from_address(from_addr),
                "description": body[:10000],
                "status": "parsed",
                "discovered_at": datetime.now(timezone.utc),
            })

        logger.info(
            "gmail_poll_complete",
            source_id=str(source_id),
            job_emails=len(results),
        )
    except Exception as exc:
        logger.error("gmail_poll_failed", source_id=str(source_id), error=str(exc))

    return results


def _extract_gmail_body(msg: dict) -> str:
    """Recursively extract plain text from Gmail API message payload."""
    import base64

    def extract(part: dict) -> str:
        mime_type = part.get("mimeType", "")
        if mime_type == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        elif mime_type.startswith("multipart/"):
            return "\n".join(extract(p) for p in part.get("parts", []))
        return ""

    return extract(msg.get("payload", {}))
