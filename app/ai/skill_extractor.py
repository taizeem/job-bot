"""
Skill extractor module.

Uses the LLM to extract required/preferred skills, experience requirements,
and salary details from job descriptions.
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from app.ai.client import ai_client

logger = logging.getLogger(__name__)


class ExtractedJobDetails(BaseModel):
    """Details extracted from a job description by AI."""
    required_skills: list[str] = Field(
        default_factory=list,
        description="Core technical or professional skills explicitly required for the role."
    )
    preferred_skills: list[str] = Field(
        default_factory=list,
        description="Nice-to-have, bonus, or secondary skills mentioned in the description."
    )
    experience_years: Optional[int] = Field(
        default=None,
        description="Minimum years of experience required for the role, if explicitly specified. Otherwise null."
    )
    salary_range: Optional[str] = Field(
        default=None,
        description="Salary range or compensation details mentioned in the text (e.g. '$120k - $150k'). Otherwise null."
    )


def extract_job_details(job_description: str) -> ExtractedJobDetails:
    """Analyze job description and extract structured skills and requirements."""
    if not job_description.strip():
        return ExtractedJobDetails()

    system_prompt = (
        "You are an expert technical recruiter. "
        "Your task is to analyze the provided job description and extract the key "
        "requirements: required skills, preferred skills, minimum experience years, "
        "and salary range. Be precise. Standardize skill names (e.g. 'React.js' to 'React', "
        "'Python Programming' to 'Python')."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Here is the job description:\n\n{job_description}"}
    ]

    logger.debug("Extracting skills and requirements from job description...")
    try:
        details = ai_client.structured_output(messages, response_model=ExtractedJobDetails)
        return details
    except Exception as e:
        logger.error("Failed to extract job details: %s", e)
        # Return empty shell to prevent pipeline crash
        return ExtractedJobDetails()
