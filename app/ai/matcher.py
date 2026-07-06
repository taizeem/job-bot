"""
AI job matching module.

Compares a job description against the candidate's primary resume to generate
a match score and formatted summary using the LLM.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.client import ai_client
from app.database.models import Job, Resume

logger = logging.getLogger(__name__)


class MatchResultSchema(BaseModel):
    """Structured response from LLM evaluation of job matching."""
    match_score: float = Field(
        description="Relevance percentage score from 0 to 100 based on overall fit."
    )
    matched_skills: list[str] = Field(
        default_factory=list,
        description="Key skills/technologies mentioned in the job description that the candidate possesses."
    )
    missing_skills: list[str] = Field(
        default_factory=list,
        description="Key skills/technologies required or preferred in the job description that the candidate lacks."
    )
    salary: Optional[str] = Field(
        default=None,
        description="Salary or compensation mentioned in the description (e.g. '$120k'), if any."
    )
    experience: Optional[str] = Field(
        default=None,
        description="Required experience level mentioned in the job description (e.g. '3 years'), if any."
    )


def build_ai_summary(match_result: MatchResultSchema) -> str:
    """Format structured match details into the requested user summary format.

    Format:
        Required
        ✓ Python
        ✓ Docker
        ✓ PostgreSQL

        Missing
        ✗ Kubernetes

        Salary
        $120k

        Experience
        3 years
    """
    lines = []
    
    if match_result.matched_skills:
        lines.append("Required")
        for skill in match_result.matched_skills:
            lines.append(f"✓ {skill}")
            
    if match_result.missing_skills:
        if lines:
            lines.append("")  # Empty line separator
        lines.append("Missing")
        for skill in match_result.missing_skills:
            lines.append(f"✗ {skill}")
            
    if match_result.salary:
        if lines:
            lines.append("")
        lines.append(f"Salary\n{match_result.salary}")
        
    if match_result.experience:
        if lines:
            lines.append("")
        lines.append(f"Experience\n{match_result.experience}")
        
    return "\n".join(lines)


def match_job_against_resume(
    job_description: str,
    resume_json: str,
) -> tuple[float, str]:
    """Calculate match score (0.0 to 1.0) and generate formatting summary.

    Args:
        job_description: The job description text.
        resume_json: JSON string representing the parsed resume (ResumeData).

    Returns:
        Tuple of (match_score_float_0_to_1, summary_markdown_str).
    """
    if not job_description.strip() or not resume_json.strip():
        return 0.0, "Missing job description or resume data."

    system_prompt = (
        "You are an expert technical interviewer and matching engine. "
        "You will receive a candidate's structured resume in JSON and a job description. "
        "Analyze the job requirements and the candidate's profile. "
        "Provide a percentage match score (0 to 100), identify matched skills, "
        "missing key skills, and extract any salary and experience requirements "
        "mentioned in the job posting."
    )

    prompt = (
        f"Candidate Resume JSON:\n{resume_json}\n\n"
        f"Job Description:\n{job_description}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]

    try:
        match_data = ai_client.structured_output(messages, response_model=MatchResultSchema)
        score = max(0.0, min(100.0, match_data.match_score)) / 100.0  # Normalize to 0.0 - 1.0
        summary = build_ai_summary(match_data)
        return score, summary
    except Exception as e:
        logger.error("AI matching calculation failed: %s", e)
        return 0.0, "Failed to compute match score due to AI completion error."


def run_matching_pipeline(db: Session) -> dict[str, int]:
    """Find all jobs in the database without a match score and score them.

    Scoring is performed against the primary resume in the database.

    Args:
        db: Active SQLAlchemy session.

    Returns:
        Summary dict containing counts of processed, matched, and failed matches.
    """
    # 1. Fetch primary resume
    primary_resume = db.query(Resume).filter(Resume.is_primary == True).first()
    if not primary_resume:
        logger.warning("No primary resume found in database. Cannot run matching pipeline.")
        return {"processed": 0, "matched": 0, "failed": 0}

    if not primary_resume.parsed_data:
        logger.warning(
            "Primary resume does not have parsed structured data. "
            "Run parse-resume first."
        )
        return {"processed": 0, "matched": 0, "failed": 0}

    # 2. Fetch jobs without match scores
    unmatched_jobs = db.query(Job).filter(Job.match_score == None).all()
    if not unmatched_jobs:
        logger.info("All jobs already have match scores.")
        return {"processed": 0, "matched": 0, "failed": 0}

    logger.info("Found %d unmatched jobs to process.", len(unmatched_jobs))
    processed = 0
    matched = 0
    deleted = 0
    failed = 0

    from app.config import settings
    from app.database.models import Application

    for job in unmatched_jobs:
        processed += 1
        try:
            score, summary = match_job_against_resume(
                job.description,
                primary_resume.parsed_data
            )
            
            # Check if job is a low match and should be deleted
            if settings.delete_unmatched_jobs and score < settings.min_match_threshold:
                # Double check no application exists before deleting (safety check)
                has_app = db.query(Application).filter(Application.job_id == job.id).first() is not None
                if not has_app:
                    db.delete(job)
                    db.commit()
                    deleted += 1
                    logger.info("Deleted job ID %d (%s) - Low Score: %.2f (Threshold: %.2f)", job.id, job.title, score, settings.min_match_threshold)
                    continue

            # Otherwise, keep the job and save the evaluation
            job.match_score = score
            job.ai_summary = summary
            db.commit()
            matched += 1
            logger.info("Matched job ID %d (%s) - Score: %.2f", job.id, job.title, score)
        except Exception as e:
            db.rollback()
            failed += 1
            logger.error("Error matching job ID %d: %s", job.id, e)

    return {
        "processed": processed,
        "matched": matched,
        "deleted": deleted,
        "failed": failed
    }
