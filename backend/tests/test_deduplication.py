"""Tests for the deduplication service."""
from __future__ import annotations

import pytest

from app.services.deduplication import compute_dedup_hash


class TestComputeDedupHash:
    def test_same_inputs_same_hash(self):
        h1 = compute_dedup_hash("Acme Corp", "Software Engineer", "https://jobs.acme.com/123")
        h2 = compute_dedup_hash("Acme Corp", "Software Engineer", "https://jobs.acme.com/123")
        assert h1 == h2

    def test_different_companies_differ(self):
        h1 = compute_dedup_hash("Acme Corp", "Engineer", "https://example.com/1")
        h2 = compute_dedup_hash("Globex Corp", "Engineer", "https://example.com/1")
        assert h1 != h2

    def test_different_titles_differ(self):
        h1 = compute_dedup_hash("Acme", "Software Engineer", "https://example.com/1")
        h2 = compute_dedup_hash("Acme", "Senior Engineer", "https://example.com/1")
        assert h1 != h2

    def test_url_fragment_stripped(self):
        """URL fragments (#...) should not affect the hash."""
        h1 = compute_dedup_hash("Acme", "SWE", "https://jobs.acme.com/123")
        h2 = compute_dedup_hash("Acme", "SWE", "https://jobs.acme.com/123#apply")
        assert h1 == h2

    def test_url_query_stripped(self):
        """UTM params and query strings should not affect the hash."""
        h1 = compute_dedup_hash("Acme", "SWE", "https://jobs.acme.com/123")
        h2 = compute_dedup_hash("Acme", "SWE", "https://jobs.acme.com/123?utm_source=handshake")
        assert h1 == h2

    def test_trailing_slash_stripped(self):
        h1 = compute_dedup_hash("Acme", "SWE", "https://jobs.acme.com/123")
        h2 = compute_dedup_hash("Acme", "SWE", "https://jobs.acme.com/123/")
        assert h1 == h2

    def test_case_insensitive_company(self):
        h1 = compute_dedup_hash("acme corp", "SWE", "https://example.com/1")
        h2 = compute_dedup_hash("ACME CORP", "SWE", "https://example.com/1")
        assert h1 == h2

    def test_case_insensitive_title(self):
        h1 = compute_dedup_hash("Acme", "software engineer", "https://example.com/1")
        h2 = compute_dedup_hash("Acme", "Software Engineer", "https://example.com/1")
        assert h1 == h2

    def test_none_url_handled(self):
        """Hashing with no URL should not raise."""
        h = compute_dedup_hash("Acme", "SWE", None)
        assert isinstance(h, str) and len(h) > 0

    def test_empty_strings_do_not_raise(self):
        h = compute_dedup_hash("", "", "")
        assert isinstance(h, str)

    def test_hash_is_hex_string(self):
        h = compute_dedup_hash("Acme", "SWE", "https://example.com")
        assert all(c in "0123456789abcdef" for c in h)

    def test_whitespace_normalized(self):
        h1 = compute_dedup_hash("  Acme  ", "  SWE  ", "https://example.com/1")
        h2 = compute_dedup_hash("Acme", "SWE", "https://example.com/1")
        assert h1 == h2
