"""
Resume parser module.

Extracts text from a resume PDF using PyMuPDF and utilizes the LLM to parse
it into structured JSON matching the ResumeData schema.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from pydantic import BaseModel, Field

from app.ai.client import ai_client

logger = logging.getLogger(__name__)


class ExperienceItem(BaseModel):
    """Represents a job role in the experience section."""
    company: str = Field(description="Name of the company or organization.")
    role: str = Field(description="Job title or role name.")
    duration: Optional[str] = Field(default=None, description="Time duration (e.g. 'Jan 2020 - Present' or '2 years').")
    highlights: list[str] = Field(
        default_factory=list,
        description="Key responsibilities, projects, achievements, and impact."
    )


class EducationItem(BaseModel):
    """Represents an educational qualification."""
    school: str = Field(description="Name of the school, university, or institution.")
    degree: Optional[str] = Field(default=None, description="Degree, major, or certificate name.")
    year: Optional[str] = Field(default=None, description="Graduation year or date range.")


class ProjectItem(BaseModel):
    """Represents a personal or professional project."""
    name: str = Field(description="Name of the project.")
    description: str = Field(description="Brief overview of what the project accomplished.")
    technologies: list[str] = Field(
        default_factory=list,
        description="List of programming languages, frameworks, or tools used in the project."
    )


class ResumeData(BaseModel):
    """Structured fields extracted from a resume PDF."""
    name: str = Field(description="The full name of the candidate.")
    email: Optional[str] = Field(default=None, description="Contact email address.")
    phone: Optional[str] = Field(default=None, description="Contact phone number.")
    summary: Optional[str] = Field(default=None, description="Professional summary or bio.")
    skills: list[str] = Field(
        default_factory=list,
        description="List of skills, technologies, databases, and methodologies."
    )
    experience: list[ExperienceItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)


def extract_text_from_pdf(pdf_path: Path | str) -> str:
    """Extract raw text from a PDF file using PyMuPDF (fitz)."""
    text = ""
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            text += page.get_text()
        return text
    except Exception as e:
        logger.error("Failed to extract text from PDF %s: %s", pdf_path, e)
        raise RuntimeError(f"PDF extraction error: {e}") from e


def parse_resume(pdf_path: Path | str) -> ResumeData:
    """Extract and parse resume PDF into structured ResumeData."""
    raw_text = extract_text_from_pdf(pdf_path)
    
    if not raw_text.strip():
        raise ValueError("Extracted PDF text is empty. Scanned PDFs are not supported in the MVP.")

    system_prompt = (
        "You are an expert ATS (Applicant Tracking System) parser. "
        "Your task is to take raw text extracted from a resume PDF and parse it into a clean, "
        "fully-structured JSON format matching the requested schema. "
        "Extract all details carefully, without ignoring any experience or skills."
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Here is the raw resume text to parse:\n\n{raw_text}"}
    ]

    logger.info("Sending resume text to LLM for parsing...")
    parsed_data = ai_client.structured_output(messages, response_model=ResumeData)
    return parsed_data
