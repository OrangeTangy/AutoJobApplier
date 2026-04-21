"""Tests for Handshake CSV, URL batch, and JSON import parsers."""
from __future__ import annotations

import json
import uuid

import pytest

from app.services.handshake_import import (
    parse_batch_urls,
    parse_handshake_csv,
    parse_json_import,
)

USER_ID = uuid.uuid4()


# ── Handshake CSV ─────────────────────────────────────────────────────────────

SAMPLE_CSV = """\
Job ID,Employer Name,Job Title,Job Type,Application URL,Location,Expiration Date
12345,Acme Corp,Software Engineer,Full-Time,https://jobs.acme.com/12345,"San Francisco, CA",2025-06-30
67890,Globex Inc,Data Analyst,Internship,https://jobs.globex.com/67890,"New York, NY",2025-07-15
"""


class TestParseHandshakeCsv:
    def test_basic_parse(self):
        jobs = parse_handshake_csv(SAMPLE_CSV, USER_ID)
        assert len(jobs) == 2

    def test_company_name_extracted(self):
        jobs = parse_handshake_csv(SAMPLE_CSV, USER_ID)
        companies = {j["company"] for j in jobs}
        assert "Acme Corp" in companies
        assert "Globex Inc" in companies

    def test_title_extracted(self):
        jobs = parse_handshake_csv(SAMPLE_CSV, USER_ID)
        titles = {j["title"] for j in jobs}
        assert "Software Engineer" in titles

    def test_url_extracted(self):
        jobs = parse_handshake_csv(SAMPLE_CSV, USER_ID)
        urls = {j["raw_url"] for j in jobs}
        assert "https://jobs.acme.com/12345" in urls

    def test_dedup_hash_present(self):
        jobs = parse_handshake_csv(SAMPLE_CSV, USER_ID)
        for j in jobs:
            assert "dedup_hash" in j
            assert j["dedup_hash"]

    def test_dedup_hashes_unique(self):
        jobs = parse_handshake_csv(SAMPLE_CSV, USER_ID)
        hashes = [j["dedup_hash"] for j in jobs]
        assert len(hashes) == len(set(hashes))

    def test_empty_csv_returns_empty_list(self):
        jobs = parse_handshake_csv("", USER_ID)
        assert jobs == []

    def test_header_only_csv_returns_empty_list(self):
        header_only = "Job ID,Employer Name,Job Title,Application URL\n"
        jobs = parse_handshake_csv(header_only, USER_ID)
        assert jobs == []

    def test_location_extracted(self):
        jobs = parse_handshake_csv(SAMPLE_CSV, USER_ID)
        locations = {j.get("location") for j in jobs}
        assert "San Francisco, CA" in locations

    def test_malformed_csv_skips_bad_rows(self):
        bad_csv = "Job ID,Employer Name,Job Title,Application URL\n,,,\n12345,Acme,SWE,https://x.com\n"
        jobs = parse_handshake_csv(bad_csv, USER_ID)
        # Should parse the valid row (and skip empty)
        assert len(jobs) >= 1


# ── URL batch ─────────────────────────────────────────────────────────────────

SAMPLE_URLS = """\
https://jobs.lever.co/acme/abc123
https://boards.greenhouse.io/globex/jobs/456
  https://myworkdayjobs.com/Acme/job/789
# this is a comment
invalid-not-a-url
https://jobs.lever.co/beta/xyz
"""


class TestParseBatchUrls:
    def test_valid_urls_extracted(self):
        jobs = parse_batch_urls(SAMPLE_URLS, USER_ID)
        urls = {j["raw_url"] for j in jobs}
        assert "https://jobs.lever.co/acme/abc123" in urls
        assert "https://boards.greenhouse.io/globex/jobs/456" in urls

    def test_whitespace_trimmed(self):
        jobs = parse_batch_urls(SAMPLE_URLS, USER_ID)
        urls = {j["raw_url"] for j in jobs}
        assert "https://myworkdayjobs.com/Acme/job/789" in urls

    def test_comments_skipped(self):
        jobs = parse_batch_urls(SAMPLE_URLS, USER_ID)
        urls = {j["raw_url"] for j in jobs}
        assert "# this is a comment" not in urls

    def test_invalid_urls_skipped(self):
        jobs = parse_batch_urls(SAMPLE_URLS, USER_ID)
        urls = {j["raw_url"] for j in jobs}
        assert "invalid-not-a-url" not in urls

    def test_dedup_hash_present(self):
        jobs = parse_batch_urls(SAMPLE_URLS, USER_ID)
        for j in jobs:
            assert "dedup_hash" in j

    def test_empty_text_returns_empty_list(self):
        jobs = parse_batch_urls("", USER_ID)
        assert jobs == []

    def test_duplicate_urls_deduplicated(self):
        dupes = "https://jobs.lever.co/acme/abc123\nhttps://jobs.lever.co/acme/abc123\n"
        jobs = parse_batch_urls(dupes, USER_ID)
        assert len(jobs) == 1


# ── JSON import ───────────────────────────────────────────────────────────────

SAMPLE_JSON = json.dumps([
    {
        "title": "Backend Engineer",
        "company": "StartupCo",
        "location": "Remote",
        "raw_url": "https://jobs.startupco.com/be-123",
        "description": "We're hiring a backend engineer...",
    },
    {
        "title": "Product Manager",
        "company": "BigCo",
        "raw_url": "https://bigco.jobs/pm-456",
    },
])


class TestParseJsonImport:
    def test_basic_parse(self):
        jobs = parse_json_import(SAMPLE_JSON, USER_ID)
        assert len(jobs) == 2

    def test_fields_extracted(self):
        jobs = parse_json_import(SAMPLE_JSON, USER_ID)
        job = next(j for j in jobs if j.get("company") == "StartupCo")
        assert job["title"] == "Backend Engineer"
        assert job["location"] == "Remote"
        assert job["raw_url"] == "https://jobs.startupco.com/be-123"

    def test_dedup_hash_present(self):
        jobs = parse_json_import(SAMPLE_JSON, USER_ID)
        for j in jobs:
            assert "dedup_hash" in j

    def test_invalid_json_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_json_import("not valid json", USER_ID)

    def test_non_array_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_json_import(json.dumps({"key": "value"}), USER_ID)

    def test_empty_array_returns_empty_list(self):
        jobs = parse_json_import("[]", USER_ID)
        assert jobs == []

    def test_missing_optional_fields_ok(self):
        minimal = json.dumps([{"raw_url": "https://example.com/job/1"}])
        jobs = parse_json_import(minimal, USER_ID)
        assert len(jobs) == 1
