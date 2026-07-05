"""
Email classification module.

Uses the LLM to classify emails received from companies regarding job applications
(interview scheduling, coding assessments, rejections, offers, etc.).
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from app.ai.client import ai_client

logger = logging.getLogger(__name__)


class EmailClassification(BaseModel):
    """Result of classifying a job-related email."""
    category: str = Field(
        description=(
            "Must be one of the following exact strings: "
            "'interview' (interview invitation or scheduling link), "
            "'assessment' (online coding challenge or cognitive test), "
            "'rejection' (notice that application is not moving forward), "
            "'offer' (job offer details or intent to offer), "
            "'followup' (confirmation of receipt or generic follow-up), "
            "'irrelevant' (not related to a job application)."
        )
    )
    company_name: Optional[str] = Field(
        default=None,
        description="The name of the company sending the email, if clearly identifiable. Otherwise null."
    )
    reasoning: str = Field(
        description="A brief explanation of why this classification category was chosen."
    )


def classify_email(subject: str, body_snippet: str) -> EmailClassification:
    """Classify email subject and body snippet using the AI Client."""
    if not subject.strip() and not body_snippet.strip():
        return EmailClassification(category="irrelevant", reasoning="Empty email content.")

    system_prompt = (
        "You are an AI assistant monitoring a job seeker's email inbox. "
        "Your task is to analyze the email subject and body snippet and classify it "
        "into one of the standard job application categories. "
        "Categories: 'interview', 'assessment', 'rejection', 'offer', 'followup', 'irrelevant'. "
        "Extract the company name if possible."
    )

    prompt = (
        f"Email Subject: {subject}\n\n"
        f"Email Snippet:\n{body_snippet}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]

    try:
        classification = ai_client.structured_output(messages, response_model=EmailClassification)
        # Ensure category value matches choices
        valid_cats = {"interview", "assessment", "rejection", "offer", "followup", "irrelevant"}
        if classification.category.lower().strip() not in valid_cats:
            logger.warning(
                "AI returned invalid category '%s'. Defaulting to 'irrelevant'.",
                classification.category
            )
            classification.category = "irrelevant"
        return classification
    except Exception as e:
        logger.error("Email classification failed: %s", e)
        return EmailClassification(
            category="irrelevant",
            reasoning=f"Error running classification: {e}"
        )
