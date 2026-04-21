"""
Handshake export parser and batch URL importer.

Accepts:
- Handshake CSV/JSON exports
- Plain text files with one URL per line
- JSON arrays of {url, title, company} objects
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger(__name__)


def _url_dedup_hash(user_id: str, url: str) -> str:
    clean = re.sub(r"[?#].*$", "", url.lower().strip())
    return hashlib.sha256(f"{user_id}|{clean}".encode()).hexdigest()


def parse_handshake_csv(content: str, user_id: uuid.UUID) -> list[dict]:
    """
    Parse a Handshake job export CSV.

    Handshake exports have columns like:
    Job Title, Employer Name, Location, Job Type, Application Deadline,
    Job URL, Description, ...
    """
    results = []
    reader = csv.DictReader(io.StringIO(content))

    # Normalize column names
    fieldnames = reader.fieldnames or []
    col_map = {f.lower().strip().replace(" ", "_"): f for f in fieldnames}

    def get(row: dict, *keys: str) -> str:
        for k in keys:
            for candidate in [k, k.replace("_", " ")]:
                for col, orig in col_map.items():
                    if candidate in col:
                        val = row.get(orig, "")
                        if val:
                            return val.strip()
        return ""

    for row in reader:
        url = get(row, "application_url", "job_url", "url", "link", "apply_url")
        title = get(row, "job_title", "title", "position")
        company = get(row, "employer_name", "company", "employer", "organization")
        location = get(row, "location", "city", "work_location")
        deadline_str = get(row, "application_deadline", "deadline", "close_date", "expiration_date")
        description = get(row, "description", "job_description", "summary")

        if not (url or title):
            continue

        dedup_hash = _url_dedup_hash(str(user_id), url or f"{company}-{title}")

        results.append({
            "user_id": user_id,
            "dedup_hash": dedup_hash,
            "raw_url": url or None,
            "title": title or None,
            "company": company or None,
            "location": location or None,
            "description": description[:5000] if description else None,
            "deadline": _parse_deadline(deadline_str),
            "status": "parsed" if (title and company) else "new",
            "discovered_at": datetime.now(timezone.utc),
        })

    logger.info("handshake_csv_parsed", count=len(results))
    return results


def parse_batch_urls(content: str, user_id: uuid.UUID) -> list[dict]:
    """
    Parse a plain text file with one URL per line.
    Lines starting with # are treated as comments.
    Duplicate URLs within the batch are deduplicated.
    """
    results = []
    seen: set[str] = set()
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not re.match(r"https?://", line):
            continue
        dedup_hash = _url_dedup_hash(str(user_id), line)
        if dedup_hash in seen:
            continue
        seen.add(dedup_hash)
        results.append({
            "user_id": user_id,
            "dedup_hash": dedup_hash,
            "raw_url": line,
            "status": "new",
            "discovered_at": datetime.now(timezone.utc),
        })
    logger.info("batch_urls_parsed", count=len(results))
    return results


def parse_json_import(content: str, user_id: uuid.UUID) -> list[dict]:
    """
    Parse a JSON array of job objects.
    Expected shape: [{url, title?, company?, location?, description?}]
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError("Expected a JSON array")

    results = []
    for item in data:
        url = item.get("raw_url") or item.get("url") or item.get("link") or item.get("apply_url") or ""
        title = item.get("title") or item.get("job_title", "")
        company = item.get("company") or item.get("employer", "")

        dedup_hash = _url_dedup_hash(str(user_id), url or f"{company}-{title}")
        results.append({
            "user_id": user_id,
            "dedup_hash": dedup_hash,
            "raw_url": url or None,
            "title": title or None,
            "company": company or None,
            "location": item.get("location"),
            "description": str(item.get("description", ""))[:5000] or None,
            "status": "parsed" if (title and company) else "new",
            "discovered_at": datetime.now(timezone.utc),
        })

    logger.info("json_import_parsed", count=len(results))
    return results


def _parse_deadline(date_str: str) -> str | None:
    """Try to parse a date string into ISO format."""
    if not date_str:
        return None
    import re
    from datetime import datetime

    formats = [
        "%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y",
        "%B %d, %Y", "%b %d, %Y", "%d %B %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None
