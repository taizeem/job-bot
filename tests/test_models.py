"""
Tests for the database models.
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import Session

from app.database.models import Job, Company, Application, Resume, Log


def test_create_job(db_session: Session):
    """Test creating a job and fetching it back."""
    job = Job(
        title="Go Developer",
        company="Google",
        url="https://google.jobs/1",
        source="lever",
        description="Write Go code.",
    )
    db_session.add(job)
    db_session.commit()

    db_job = db_session.query(Job).filter(Job.company == "Google").first()
    assert db_job is not None
    assert db_job.id is not None
    assert db_job.title == "Go Developer"
    assert db_job.remote is False  # Default value
    assert db_job.scraped_at is not None  # Server default


def test_create_company(db_session: Session):
    """Test creating a company."""
    company = Company(
        name="Stripe",
        greenhouse_token="stripe",
        website="https://stripe.com",
    )
    db_session.add(company)
    db_session.commit()

    db_comp = db_session.query(Company).filter(Company.name == "Stripe").first()
    assert db_comp is not None
    assert db_comp.is_active is True  # Default
    assert db_comp.greenhouse_token == "stripe"


def test_create_application_relationship(db_session: Session):
    """Test application linked to job and checking cascades."""
    job = Job(
        title="React Developer",
        company="Facebook",
        url="https://meta.jobs/1",
        source="lever",
        description="Write React.",
    )
    db_session.add(job)
    db_session.commit()

    application = Application(
        job_id=job.id,
        status="applied",
        applied_at=datetime.utcnow(),
    )
    db_session.add(application)
    db_session.commit()

    # Query application and check relationship
    db_app = db_session.query(Application).filter(Application.job_id == job.id).first()
    assert db_app is not None
    assert db_app.status == "applied"
    assert db_app.job.company == "Facebook"

    # Test cascade delete: deleting job should delete application
    db_session.delete(job)
    db_session.commit()

    orphan_app = db_session.query(Application).filter(Application.id == db_app.id).first()
    assert orphan_app is None  # Cascade delete succeeded
