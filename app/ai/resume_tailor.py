"""
Resume tailoring module.

Uses the LLM to tailor a candidate's resume for a specific job description
by highlighting relevant experience, reordering skills, rewriting the summary,
and optimizing wording.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.ai.client import ai_client
from app.config import settings

logger = logging.getLogger(__name__)


def tailor_resume(
    resume_json: str,
    job_title: str,
    company_name: str,
    job_description: str,
) -> str:
    """Generate a tailored Markdown version of the candidate's resume for a job.

    Args:
        resume_json: Parsed resume JSON string (ResumeData).
        job_title: Title of target job.
        company_name: Name of hiring company.
        job_description: Full job description text.

    Returns:
        Tailored resume in Markdown format.
    """
    system_prompt = (
        "You are an expert resume writer and career coach. "
        "Your task is to take a candidate's structured resume (JSON) and a target "
        "job description, and generate a tailored resume in clean Markdown format. "
        "Focus on: "
        "1. Rewriting the professional summary to directly address the job's core challenges. "
        "2. Reordering and prioritizing skills to match the job description's keywords first. "
        "3. Emphasizing relevant projects and work experience highlights while retaining chronological order. "
        "4. Improving wording to reflect terms used in the job description. "
        "Do NOT invent experiences or skills the candidate doesn't have. "
        "Format the output strictly as professional Markdown, without any intro/outro text."
    )

    prompt = (
        f"Target Job: {job_title} at {company_name}\n\n"
        f"Candidate Resume JSON:\n{resume_json}\n\n"
        f"Job Description:\n{job_description}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]

    logger.info("Generating tailored resume for %s at %s...", job_title, company_name)
    tailored_markdown = ai_client.chat_completion(messages, temperature=0.3)
    return tailored_markdown


def save_tailored_resume(
    job_id: int,
    company_name: str,
    tailored_content: str,
) -> Path:
    """Save tailored resume to data/resumes directory.

    Returns:
        The Path to the saved file.
    """
    settings.ensure_dirs()
    # Sanitize company name for filename
    safe_company = "".join(c for c in company_name if c.isalnum() or c in ("-", "_")).strip()
    filename = f"tailored_{safe_company}_{job_id}.md"
    file_path = settings.resumes_dir / filename
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(tailored_content)
        
    logger.info("Saved tailored resume to: %s", file_path)
    return file_path
