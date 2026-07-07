"""
Keyword-based job matching engine.
Evaluates job postings against a UserProfile using skills, country/location, and title keywords.
"""

from __future__ import annotations

import json
import logging
from typing import Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.database.models import Job, UserProfile, Application, Log

logger = logging.getLogger(__name__)


def compute_keyword_score(profile_data: dict, job: Job) -> tuple[float, str]:
    """Compute keyword match score (0.0 to 1.0) and detailed summary.

    profile_data structure:
      {
        "skills": list[str],
        "country": str,
        "preferred_locations": list[str],
        "preferred_job_titles": list[str]
      }
    """
    profile_skills = [s.lower().strip() for s in profile_data.get("skills", []) if s.strip()]
    profile_country = (profile_data.get("country") or "").lower().strip()
    preferred_locs = [l.lower().strip() for l in profile_data.get("preferred_locations", []) if l.strip()]
    preferred_titles = [t.lower().strip() for t in profile_data.get("preferred_job_titles", []) if t.strip()]

    # Load job fields
    job_title = (job.title or "").lower()
    job_description = (job.description or "").lower()
    
    # 1. Parse job skills
    job_skills = []
    if job.skills:
        try:
            job_skills = json.loads(job.skills)
            if isinstance(job_skills, list):
                job_skills = [s.lower().strip() for s in job_skills if s.strip()]
            else:
                job_skills = []
        except Exception:
            job_skills = []
            
    # If job.skills is empty, try to extract some from description using a simple word scan
    if not job_skills:
        # Fallback: scan for any profile skills in description
        for ps in profile_skills:
            if f" {ps} " in f" {job_description} " or f" {ps}," in f" {job_description} " or f" {ps}." in f" {job_description} ":
                job_skills.append(ps)

    # ── A. Skills Match (50% weight) ──
    matched_skills = []
    missing_skills = []
    
    # Check explicitly listed job skills
    unique_job_skills = list(set(job_skills))
    if unique_job_skills:
        for js in unique_job_skills:
            # Fuzzy match: is the job skill a substring of any profile skill, or vice versa?
            found = False
            for ps in profile_skills:
                if ps == js or ps in js or js in ps:
                    found = True
                    matched_skills.append(js)
                    break
            if not found:
                missing_skills.append(js)
        
        skill_score = len(matched_skills) / len(unique_job_skills) if unique_job_skills else 1.0
    else:
        # If no job skills are declared/found, evaluate based on profile skill density
        matches_count = sum(1 for ps in profile_skills if ps in job_description)
        skill_score = min(1.0, matches_count / max(1, len(profile_skills)))
        matched_skills = [ps for ps in profile_skills if ps in job_description]
        
    # ── B. Location Match (20% weight) ──
    location_score = 0.0
    job_location_raw = (job.location or "").lower()
    
    is_remote = job.remote or "remote" in job_location_raw or "anywhere" in job_location_raw
    
    if is_remote:
        location_score = 1.0  # Remote matches all
    elif profile_country and (profile_country in job_location_raw):
        location_score = 1.0
    else:
        # Check preferred locations
        for loc in preferred_locs:
            if loc in job_location_raw:
                location_score = 1.0
                break
                
    # ── C. Title Match (20% weight) ──
    title_score = 0.0
    matched_title = ""
    for title in preferred_titles:
        if title in job_title or job_title in title:
            title_score = 1.0
            matched_title = title
            break
            
    # ── D. Density/Match Bonus (10% weight) ──
    # Extra check of how many profile skills appear in the full job description
    density_matches = sum(1 for ps in profile_skills if ps in job_description)
    density_score = min(1.0, density_matches / max(5, len(profile_skills)))

    # Calculate overall weighted score
    overall_score = (
        (skill_score * 0.5) +
        (location_score * 0.2) +
        (title_score * 0.2) +
        (density_score * 0.1)
    )
    
    # ── Build formatting summary ──
    # Emulate the build_ai_summary format:
    # Required
    # ✓ Python
    # ✓ Docker
    # ✓ PostgreSQL
    #
    # Missing
    # ✗ Kubernetes
    #
    # Location
    # Match (Remote)
    #
    # Preferred Title Match
    # Software Engineer
    lines = []
    
    if matched_skills:
        lines.append("Required")
        for skill in sorted(list(set(matched_skills)))[:15]:
            lines.append(f"✓ {skill.title()}")
            
    if missing_skills:
        if lines:
            lines.append("")
        lines.append("Missing")
        for skill in sorted(list(set(missing_skills)))[:15]:
            lines.append(f"✗ {skill.title()}")
            
    if lines:
        lines.append("")
    lines.append("Location")
    if is_remote:
        lines.append("✓ Matches (Remote position)")
    elif location_score > 0:
        lines.append(f"✓ Matches ({job.location})")
    else:
        lines.append(f"✗ No Match (Job: {job.location or 'Not specified'})")
        
    if preferred_titles:
        lines.append("")
        lines.append("Preferred Title Match")
        if title_score > 0:
            lines.append(f"✓ Match ({matched_title.title()})")
        else:
            lines.append(f"✗ No Match (Job: {job.title})")
            
    return overall_score, "\n".join(lines)


def run_keyword_matching_pipeline(db: Session) -> dict[str, int]:
    """Score unmatched job listings based on keywords in the UserProfile."""
    profile = db.query(UserProfile).first()
    if not profile:
        logger.warning("No UserProfile found in database. Cannot run keyword matching.")
        return {"processed": 0, "matched": 0, "deleted": 0, "failed": 0}

    # Load profile data
    try:
        profile_skills = json.loads(profile.skills) if profile.skills else []
        preferred_titles = json.loads(profile.preferred_job_titles) if profile.preferred_job_titles else []
        preferred_locs = json.loads(profile.preferred_locations) if profile.preferred_locations else []
    except Exception as e:
        logger.error("Failed to parse UserProfile JSON fields: %s", e)
        return {"processed": 0, "matched": 0, "deleted": 0, "failed": 0}

    profile_data = {
        "skills": profile_skills,
        "country": profile.country or "",
        "preferred_locations": preferred_locs,
        "preferred_job_titles": preferred_titles,
    }

    # Query unmatched jobs
    unmatched_jobs = db.query(Job).filter(Job.match_score == None).all()
    if not unmatched_jobs:
        logger.info("All jobs already evaluated.")
        return {"processed": 0, "matched": 0, "deleted": 0, "failed": 0}

    processed = 0
    matched = 0
    deleted = 0
    failed = 0

    for job in unmatched_jobs:
        processed += 1
        try:
            score, summary = compute_keyword_score(profile_data, job)
            
            # Apply threshold checks
            if settings.delete_unmatched_jobs and score < settings.min_match_threshold:
                # Keep job if application exists (safety check)
                has_app = db.query(Application).filter(Application.job_id == job.id).first() is not None
                if not has_app:
                    db.delete(job)
                    db.commit()
                    deleted += 1
                    continue

            # Update match metrics
            job.match_score = score
            job.ai_summary = summary
            db.commit()
            matched += 1
        except Exception as e:
            db.rollback()
            failed += 1
            logger.error("Error matching job %d: %s", job.id, e)

    # Log summary
    if matched > 0 or deleted > 0:
        db.add(Log(
            event="match",
            source="Keyword Matcher",
            message=f"Scored {matched} jobs, deleted {deleted} low-match jobs."
        ))
        db.commit()

    return {
        "processed": processed,
        "matched": matched,
        "deleted": deleted,
        "failed": failed
    }
