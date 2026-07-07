"""
Database cleanup utilities.

Provides functions to prune low-relevance jobs from the SQLite database.
"""

from __future__ import annotations

import logging
from sqlalchemy.orm import Session
from app.database.models import Job, Application, Log

logger = logging.getLogger(__name__)


def cleanup_low_matching_jobs(db: Session, threshold: float = 0.70) -> int:
    """Delete evaluated jobs with a match score below the specified threshold.

    Keeps jobs that have an associated job application (safety check).

    Args:
        db: Active SQLAlchemy session.
        threshold: Score threshold (0.0 to 1.0) below which jobs will be pruned.

    Returns:
        The number of deleted job postings.
    """
    try:
        # Find all jobs with score below threshold
        low_jobs = db.query(Job).filter(
            Job.match_score.isnot(None),
            Job.match_score < threshold
        ).all()

        if not low_jobs:
            logger.info("No low-matching jobs found to prune.")
            return 0

        deleted_count = 0
        for job in low_jobs:
            # Check if there is an active job application
            has_app = db.query(Application).filter(Application.job_id == job.id).first() is not None
            if not has_app:
                db.delete(job)
                deleted_count += 1

        if deleted_count > 0:
            db.commit()
            # Log cleanup event to database logs
            db.add(Log(
                event="cleanup",
                source="Database Cleaner",
                message=f"Cleaned up {deleted_count} jobs with match score below {int(threshold * 100)}%."
            ))
            db.commit()
            logger.info("Cleaned up %d low-matching jobs successfully.", deleted_count)
        else:
            logger.info("Checked %d jobs; none were deleted due to active applications.", len(low_jobs))

        return deleted_count

    except Exception as e:
        db.rollback()
        logger.error("Failed to execute job cleanup: %s", e)
        return 0
