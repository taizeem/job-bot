"""
Job deduplication and storage module.

Provides two main functions:

``deduplicate_jobs``
    Filters out jobs that already exist in the database (by URL or
    fingerprint), keeping the richer record when a fingerprint match
    is found from a different source.

``store_jobs``
    Deduplicates and then bulk-inserts new ``Job`` ORM objects into
    the database.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.database.models import Job

logger = logging.getLogger(__name__)


def deduplicate_jobs(
    new_jobs: list[dict[str, Any]],
    db_session: Session,
) -> list[dict[str, Any]]:
    """Filter out duplicate jobs that already exist in the database.

    Deduplication strategy:
        1. **URL match** — exact match on ``url`` → skip the new job.
        2. **Fingerprint match** — same ``fingerprint`` found in DB:
           - If from a *different source*, keep whichever record is
             "richer" (longer description, has salary, newer scrape).
           - If from the *same source*, skip.
        3. Everything else is considered a truly new job.

    Args:
        new_jobs: List of normalized job dicts from scrapers.
        db_session: Active SQLAlchemy session.

    Returns:
        Subset of ``new_jobs`` that are genuinely new.
    """
    if not new_jobs:
        return []

    # Collect all URLs and fingerprints from the batch
    urls = {j.get("url") for j in new_jobs if j.get("url")}
    fingerprints = {
        j.get("fingerprint") for j in new_jobs if j.get("fingerprint")
    }

    # Bulk-query existing records
    existing_by_url: set[str] = set()
    if urls:
        rows = (
            db_session.query(Job.url)
            .filter(Job.url.in_(urls))
            .all()
        )
        existing_by_url = {r[0] for r in rows if r[0]}

    existing_by_fp: dict[str, Job] = {}
    if fingerprints:
        rows_fp = (
            db_session.query(Job)
            .filter(Job.fingerprint.in_(fingerprints))
            .all()
        )
        existing_by_fp = {j.fingerprint: j for j in rows_fp if j.fingerprint}

    unique_jobs: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_fps: set[str] = set()

    for job in new_jobs:
        url = job.get("url", "")
        fp = job.get("fingerprint", "")

        # 1) Skip exact URL duplicates
        if url and (url in existing_by_url or url in seen_urls):
            logger.debug("Skipping URL duplicate: %s", url)
            continue

        # 2) Check fingerprint match
        if fp and fp in existing_by_fp:
            existing_job = existing_by_fp[fp]
            if existing_job.source == job.get("source"):
                logger.debug(
                    "Skipping same-source fingerprint duplicate: %s", fp
                )
                continue

            # Different source — keep the richer record
            if _is_richer(job, existing_job):
                # Update existing record with richer data
                _update_existing(existing_job, job, db_session)
                logger.debug(
                    "Updated existing job (fp=%s) with richer data from %s",
                    fp,
                    job.get("source"),
                )
            else:
                logger.debug(
                    "Existing job (fp=%s) is richer — skipping new from %s",
                    fp,
                    job.get("source"),
                )
            continue

        # 3) Also deduplicate within the current batch
        if fp and fp in seen_fps:
            logger.debug("Skipping intra-batch fingerprint duplicate: %s", fp)
            continue

        # Genuinely new
        if url:
            seen_urls.add(url)
        if fp:
            seen_fps.add(fp)
        unique_jobs.append(job)

    logger.info(
        "Deduplication: %d input → %d new (skipped %d)",
        len(new_jobs),
        len(unique_jobs),
        len(new_jobs) - len(unique_jobs),
    )
    return unique_jobs


def filter_by_profile(
    jobs: list[dict[str, Any]],
    db_session: Session,
) -> list[dict[str, Any]]:
    """Filter out scraped jobs that don't match candidate skills, location, or preferred titles."""
    from app.database.models import UserProfile, Resume
    import re

    # Try UserProfile first
    profile = db_session.query(UserProfile).first()
    skills = []
    preferred_titles = []
    preferred_locs = []
    country = ""
    candidate_loc = ""
    using_profile = False

    if profile and profile.name:
        using_profile = True
        try:
            skills = json.loads(profile.skills) if profile.skills else []
            preferred_titles = json.loads(profile.preferred_job_titles) if profile.preferred_job_titles else []
            preferred_locs = json.loads(profile.preferred_locations) if profile.preferred_locations else []
            country = profile.country or ""
            candidate_loc = profile.location or ""
        except Exception as e:
            logger.warning("Failed to parse UserProfile JSON fields during scraping filter: %s", e)
            using_profile = False

    if not using_profile:
        # Fallback to legacy Resume
        resume = db_session.query(Resume).filter(Resume.is_primary == True).first()
        if not resume or not resume.parsed_data:
            logger.info("No UserProfile or primary Resume found in DB. Keeping all scraped jobs.")
            return jobs
        try:
            resume_data = json.loads(resume.parsed_data)
            skills = resume_data.get("skills", [])
            candidate_loc = resume_data.get("location", "")
        except Exception:
            logger.warning("Failed to parse Resume JSON during scraping filter.")
            return jobs

    # Normalize fields
    skills = [s.strip().lower() for s in skills if s.strip()]
    preferred_titles = [t.strip().lower() for t in preferred_titles if t.strip()]
    preferred_locs = [l.strip().lower() for l in preferred_locs if l.strip()]
    country = country.strip().lower()
    candidate_loc = candidate_loc.strip().lower()

    if not skills:
        logger.info("No skills defined in profile/resume. Keeping all scraped jobs.")
        return jobs

    filtered = []
    for job in jobs:
        title = (job.get("title") or "").lower()
        desc = (job.get("description") or "").lower()
        location_raw = (job.get("location") or "").lower()
        is_remote = job.get("remote", False) or "remote" in location_raw or "anywhere" in location_raw
        
        job_skills_tags = []
        # If scraper normalized skills lists
        if isinstance(job.get("skills"), list):
            job_skills_tags = [s.lower() for s in job["skills"] if s]
        elif isinstance(job.get("skills"), str):
            try:
                parsed = json.loads(job["skills"])
                if isinstance(parsed, list):
                    job_skills_tags = [s.lower() for s in parsed if s]
            except Exception:
                pass

        # 1. Skills overlap check:
        # Does the job description/title/tags mention at least one candidate skill?
        has_skill_match = False
        
        # Direct match on job tags
        for s in job_skills_tags:
            if s in skills:
                has_skill_match = True
                break
                
        # Substring/word-boundary check in title/description
        if not has_skill_match:
            for skill in skills:
                if len(skill) <= 3:
                    pattern = rf"\b{re.escape(skill)}\b"
                    if re.search(pattern, title) or re.search(pattern, desc):
                        has_skill_match = True
                        break
                else:
                    if skill in title or skill in desc:
                        has_skill_match = True
                        break
                        
        if not has_skill_match:
            logger.debug("Filtering out job %s - no skill overlap.", job.get("title"))
            continue

        # 2. Location check:
        # If job is remote, it always matches. Otherwise, check location keywords.
        if not is_remote:
            location_match = False
            # Check country
            if country and country in location_raw:
                location_match = True
            # Check candidate location
            if not location_match and candidate_loc and (candidate_loc in location_raw or location_raw in candidate_loc):
                location_match = True
            # Check preferred locations
            if not location_match:
                for loc in preferred_locs:
                    if loc in location_raw:
                        location_match = True
                        break
            # If onsite/hybrid and mismatch, skip it
            if not location_match and (country or preferred_locs or candidate_loc):
                logger.debug("Filtering out job %s - location mismatch.", job.get("title"))
                continue

        # 3. Title check:
        # If user defined preferred job titles, check if at least one matches the job title.
        if preferred_titles:
            title_match = False
            for t in preferred_titles:
                if t in title or title in t:
                    title_match = True
                    break
            if not title_match:
                logger.debug("Filtering out job %s - preferred title mismatch.", job.get("title"))
                continue

        filtered.append(job)

    logger.info("Profile Filter: Kept %d of %d scraped jobs based on profile match", len(filtered), len(jobs))
    return filtered



def store_jobs(
    jobs: list[dict[str, Any]],
    db_session: Session,
) -> int:
    """Deduplicate and store new jobs in the database.

    Args:
        jobs: List of normalized job dicts from scrapers.
        db_session: Active SQLAlchemy session.

    Returns:
        Count of newly inserted jobs.
    """
    # Filter jobs based on resume profile before deduplication and storage
    filtered_jobs = filter_by_profile(jobs, db_session)
    unique = deduplicate_jobs(filtered_jobs, db_session)

    if not unique:
        logger.info("No new jobs to store after filtering and deduplication")
        return 0

    added = 0
    for job_dict in unique:
        try:
            job_obj = Job(
                title=job_dict.get("title"),
                company=job_dict.get("company"),
                location=job_dict.get("location"),
                remote=job_dict.get("remote"),
                salary=job_dict.get("salary"),
                employment_type=job_dict.get("employment_type"),
                experience=job_dict.get("experience"),
                skills=job_dict.get("skills"),
                description=job_dict.get("description"),
                url=job_dict.get("url"),
                source=job_dict.get("source"),
                posted_date=job_dict.get("posted_date"),
                scraped_at=job_dict.get("scraped_at", datetime.utcnow()),
                match_score=job_dict.get("match_score"),
                ai_summary=job_dict.get("ai_summary"),
                fingerprint=job_dict.get("fingerprint"),
            )
            db_session.add(job_obj)
            added += 1
        except Exception as exc:
            logger.warning("Failed to create Job ORM object: %s", exc)
            continue

    try:
        db_session.commit()
        logger.info("Stored %d new jobs in the database", added)
    except Exception as exc:
        db_session.rollback()
        logger.error("Database commit failed: %s", exc)
        added = 0

    return added


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------


def _is_richer(
    new_job: dict[str, Any],
    existing_job: Job,
) -> bool:
    """Determine if the new job record is richer than the existing one.

    "Richer" means:
        - Longer description, OR
        - Has salary when existing doesn't, OR
        - Newer ``scraped_at`` timestamp.
    """
    score_new = 0
    score_existing = 0

    # Description length
    new_desc = new_job.get("description", "") or ""
    existing_desc = existing_job.description or ""
    if len(new_desc) > len(existing_desc):
        score_new += 2
    elif len(existing_desc) > len(new_desc):
        score_existing += 2

    # Salary presence
    if new_job.get("salary") and not existing_job.salary:
        score_new += 1
    elif existing_job.salary and not new_job.get("salary"):
        score_existing += 1

    # Freshness
    new_scraped = new_job.get("scraped_at")
    existing_scraped = existing_job.scraped_at
    
    # Strip timezone info for consistent comparison
    if new_scraped and new_scraped.tzinfo is not None:
        new_scraped = new_scraped.replace(tzinfo=None)
    if existing_scraped and existing_scraped.tzinfo is not None:
        existing_scraped = existing_scraped.replace(tzinfo=None)
        
    if new_scraped and existing_scraped and new_scraped > existing_scraped:
        score_new += 1
    elif existing_scraped and (not new_scraped or existing_scraped > new_scraped):
        score_existing += 1

    return score_new > score_existing


def _update_existing(
    existing_job: Job,
    new_data: dict[str, Any],
    db_session: Session,
) -> None:
    """Update an existing Job record with data from a richer new record."""
    update_fields = [
        "title",
        "company",
        "location",
        "remote",
        "salary",
        "employment_type",
        "experience",
        "skills",
        "description",
        "posted_date",
        "scraped_at",
    ]
    for field in update_fields:
        new_val = new_data.get(field)
        if new_val is not None:
            setattr(existing_job, field, new_val)

    try:
        db_session.commit()
    except Exception as exc:
        db_session.rollback()
        logger.error("Failed to update existing job: %s", exc)
