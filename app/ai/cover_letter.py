"""
Cover letter generation module.

Uses the LLM to generate a customized cover letter for a specific job
based on the candidate's resume and the job description.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.ai.client import ai_client
from app.config import settings

logger = logging.getLogger(__name__)


def generate_cover_letter(
    resume_json: str,
    job_title: str,
    company_name: str,
    job_description: str,
) -> str:
    """Generate a customized cover letter in Markdown format.

    Args:
        resume_json: Parsed resume JSON string (ResumeData).
        job_title: Title of target job.
        company_name: Name of hiring company.
        job_description: Full job description text.

    Returns:
        Generated cover letter in Markdown.
    """
    system_prompt = (
        "You are an expert copywriter and career coach. "
        "Your task is to write a highly professional, compelling, and customized "
        "cover letter based on a candidate's resume and a target job description. "
        "The letter should: "
        "1. Be addressed to the hiring manager at the specified company. "
        "2. Directly explain why the candidate is interested in this specific role and company. "
        "3. Highlight 2-3 key accomplishments from the candidate's experience that map perfectly "
        "   to the core challenges in the job description. "
        "4. End with a professional call to action. "
        "Keep it concise, engaging, and under 400 words. "
        "Do NOT invent achievements. "
        "Format the output strictly as professional Markdown (excluding contact headers), "
        "starting directly with the salutation (e.g., 'Dear Hiring Team at...')."
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

    logger.info("Generating cover letter for %s at %s...", job_title, company_name)
    cover_letter = ai_client.chat_completion(messages, temperature=0.5)
    return cover_letter


def save_cover_letter(
    job_id: int,
    company_name: str,
    content: str,
) -> Path:
    """Save cover letter to data/cover_letters directory.

    Returns:
        The Path to the saved file.
    """
    settings.ensure_dirs()
    # Sanitize company name for filename
    safe_company = "".join(c for c in company_name if c.isalnum() or c in ("-", "_")).strip()
    filename = f"cover_letter_{safe_company}_{job_id}.md"
    file_path = settings.cover_letters_dir / filename
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    logger.info("Saved cover letter to: %s", file_path)
    return file_path
