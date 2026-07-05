"""
Tests for the deduplication and storage logic.
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import Session

from app.database.models import Job
from app.scrapers.dedup import deduplicate_jobs, store_jobs


def test_dedup_url_exact(db_session: Session):
    """Test that jobs with identical URLs are filtered out."""
    # Seed one existing job
    existing = Job(
        title="Software Engineer",
        company="Acme Corp",
        url="https://acme.jobs/1",
        source="remoteok",
        description="A cool python role.",
        fingerprint="fp1",
    )
    db_session.add(existing)
    db_session.commit()

    # Create new batch containing the duplicate URL
    new_jobs = [
        {
            "title": "Software Engineer",
            "company": "Acme Corp",
            "url": "https://acme.jobs/1",  # Duplicate URL
            "source": "remotive",
            "description": "A cool python role with new description.",
            "fingerprint": "fp1",
        },
        {
            "title": "Data Scientist",
            "company": "Acme Corp",
            "url": "https://acme.jobs/2",  # New URL
            "source": "remoteok",
            "description": "Data role.",
            "fingerprint": "fp2",
        }
    ]

    unique = deduplicate_jobs(new_jobs, db_session)
    assert len(unique) == 1
    assert unique[0]["url"] == "https://acme.jobs/2"


def test_dedup_fingerprint_same_source(db_session: Session):
    """Test that fingerprint match from the same source is skipped."""
    existing = Job(
        title="Software Engineer",
        company="Acme Corp",
        url="https://acme.jobs/1",
        source="remoteok",
        description="A cool python role.",
        fingerprint="fp1",
    )
    db_session.add(existing)
    db_session.commit()

    new_jobs = [
        {
            "title": "Software Engineer",
            "company": "Acme Corp",
            "url": "https://acme.jobs/1-alternate",  # Different URL
            "source": "remoteok",                    # Same source
            "description": "Python role.",
            "fingerprint": "fp1",                    # Same fingerprint
        }
    ]

    unique = deduplicate_jobs(new_jobs, db_session)
    assert len(unique) == 0


def test_dedup_fingerprint_different_source_richer_new(db_session: Session):
    """Test that a different-source duplicate updates DB if new is richer."""
    existing = Job(
        title="Software Engineer",
        company="Acme Corp",
        url="https://acme.jobs/1",
        source="remoteok",
        description="Short description.",
        fingerprint="fp1",
        scraped_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    db_session.add(existing)
    db_session.commit()

    new_jobs = [
        {
            "title": "Software Engineer",
            "company": "Acme Corp",
            "url": "https://acme.jobs/1-alternate",  # Different URL
            "source": "remotive",                    # Different source
            "description": "Much longer and detailed description of the role.", # Richer
            "salary": "$120,000",                    # Richer
            "fingerprint": "fp1",
            "scraped_at": datetime(2026, 7, 5, tzinfo=timezone.utc),
        }
    ]

    unique = deduplicate_jobs(new_jobs, db_session)
    # Because it matched existing fp and was richer, it should update existing record in place
    # and return an empty list of "new" jobs to insert.
    assert len(unique) == 0
    
    # Verify the existing record was updated
    db_session.refresh(existing)
    assert existing.salary == "$120,000"
    assert "Much longer" in existing.description


def test_store_jobs(db_session: Session):
    """Test helper for storing jobs in the database."""
    new_jobs = [
        {
            "title": "Developer",
            "company": "Figma",
            "url": "https://figma.jobs/1",
            "source": "greenhouse",
            "description": "Build Figma.",
            "fingerprint": "figma1",
        }
    ]

    count = store_jobs(new_jobs, db_session)
    assert count == 1

    stored = db_session.query(Job).first()
    assert stored is not None
    assert stored.title == "Developer"
    assert stored.company == "Figma"
