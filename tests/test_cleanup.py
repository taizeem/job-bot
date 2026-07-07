"""
Tests for the database cleanup utilities.
"""

from __future__ import annotations

import json
from sqlalchemy.orm import Session
from app.database.models import Job, Application
from app.database.cleanup import cleanup_low_matching_jobs


def test_cleanup_low_matching_jobs(db_session: Session):
    """Test pruning jobs with match scores below 70% threshold."""
    # Job 1: Match score >= 70% (keep)
    job1 = Job(
        title="Python Developer",
        company="Tech Inc",
        url="https://tech.co/jobs/1",
        source="lever",
        description="Write Python.",
        match_score=0.75
    )

    # Job 2: Match score < 70% (delete)
    job2 = Job(
        title="Manual QA Tester",
        company="Oldschool Inc",
        url="https://oldschool.co/jobs/2",
        source="lever",
        description="Manual testing.",
        match_score=0.45
    )

    # Job 3: Match score < 70% but has active application (keep)
    job3 = Job(
        title="Linux Administrator",
        company="Enterprise Corp",
        url="https://enterprise.co/jobs/3",
        source="lever",
        description="Sys admin.",
        match_score=0.55
    )

    # Job 4: Unmatched job (keep)
    job4 = Job(
        title="Data Engineer",
        company="BigData Co",
        url="https://bigdata.co/jobs/4",
        source="lever",
        description="Spark and SQL.",
        match_score=None
    )

    db_session.add_all([job1, job2, job3, job4])
    db_session.commit()

    # Add active application to Job 3
    app = Application(
        job_id=job3.id,
        status="applied"
    )
    db_session.add(app)
    db_session.commit()

    # Execute cleanup
    deleted = cleanup_low_matching_jobs(db_session, threshold=0.70)
    assert deleted == 1  # Only Job 2 should be deleted

    # Query remaining jobs
    remaining_ids = [j.id for j in db_session.query(Job.id).all()]
    assert job1.id in remaining_ids
    assert job2.id not in remaining_ids
    assert job3.id in remaining_ids
    assert job4.id in remaining_ids
