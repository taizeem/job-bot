"""
Tests for individual job scrapers and their normalization functions.
"""

from __future__ import annotations

import json
from datetime import datetime
import pytest

from app.scrapers.remoteok import RemoteOKScraper
from app.scrapers.remotive import RemotiveScraper


def test_remoteok_normalization():
    """Test RemoteOKScraper converts raw API response fields correctly."""
    scraper = RemoteOKScraper()
    raw = {
        "id": "12345",
        "position": "Senior Backend Developer",
        "company": "Acme Corp",
        "location": "Remote",
        "salary_min": 100000,
        "salary_max": 140000,
        "tags": ["python", "django"],
        "url": "https://remoteok.com/remote-jobs/12345",
        "date": "2026-07-01T12:00:00Z",
        "description": "<p>We want a Python developer.</p>",
    }

    normalized = scraper.normalize(raw)
    assert normalized["title"] == "Senior Backend Developer"
    assert normalized["company"] == "Acme Corp"
    assert normalized["location"] == "Remote"
    assert normalized["remote"] is True
    assert normalized["salary"] == "$100,000 - $140,000"
    assert "Python" in normalized["description"]
    assert "django" in json.loads(normalized["skills"])
    assert isinstance(normalized["posted_date"], datetime)


def test_remotive_normalization():
    """Test RemotiveScraper converts raw API fields correctly."""
    scraper = RemotiveScraper()
    raw = {
        "id": 98765,
        "title": "Full Stack Engineer",
        "company_name": "Stripe",
        "candidate_required_location": "US/Canada",
        "salary": "$150,000",
        "tags": ["react", "typescript"],
        "url": "https://remotive.com/remote-jobs/98765",
        "publication_date": "2026-07-03T10:00:00",
        "description": "<div>React developer needed.</div>",
        "job_type": "full_time"
    }

    normalized = scraper.normalize(raw)
    assert normalized["title"] == "Full Stack Engineer"
    assert normalized["company"] == "Stripe"
    assert normalized["location"] == "US/Canada"
    assert normalized["salary"] == "$150,000"
    assert "react" in json.loads(normalized["skills"])
    assert normalized["employment_type"] == "Full-time"
    assert isinstance(normalized["posted_date"], datetime)
