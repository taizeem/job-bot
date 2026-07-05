"""
SQLAlchemy 2.0 ORM models for the Job Bot application.

Models
------
- :class:`Job` — Scraped job postings with AI enrichment fields.
- :class:`Company` — Companies with optional ATS API tokens.
- :class:`Application` — Tracks application status per job.
- :class:`Resume` — Stored resumes with parsed JSON data.
- :class:`Log` — Application event log for auditing and debugging.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Text, func
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


# ── Job ──────────────────────────────────────────────────────────────────────


class Job(Base):
    """A scraped job posting.

    Attributes:
        id: Primary key.
        title: Job title.
        company: Hiring company name.
        location: Job location (city, state, country).
        remote: Whether the position is remote.
        salary: Salary range or amount as free-text.
        employment_type: E.g. full-time, part-time, contract.
        experience: Required experience level.
        skills: JSON-serialised list of required skills.
        description: Full job description text.
        url: Unique URL of the job posting.
        source: Where the job was scraped from.
        posted_date: When the job was originally posted.
        scraped_at: Timestamp when we scraped the listing.
        match_score: AI-computed relevance score (0.0 – 1.0).
        ai_summary: AI-generated summary of the posting.
        fingerprint: Content hash for deduplication.
        applications: Related :class:`Application` records.
    """

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(nullable=False)
    company: Mapped[str] = mapped_column(nullable=False)
    location: Mapped[Optional[str]] = mapped_column(default=None)
    remote: Mapped[bool] = mapped_column(default=False)
    salary: Mapped[Optional[str]] = mapped_column(default=None)
    employment_type: Mapped[Optional[str]] = mapped_column(default=None)
    experience: Mapped[Optional[str]] = mapped_column(default=None)
    skills: Mapped[Optional[str]] = mapped_column(default=None)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(unique=True, nullable=False)
    source: Mapped[str] = mapped_column(nullable=False)
    posted_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=None
    )
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    match_score: Mapped[Optional[float]] = mapped_column(Float, default=None)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, default=None)
    fingerprint: Mapped[Optional[str]] = mapped_column(default=None, index=True)

    # Relationships
    applications: Mapped[list["Application"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )



    def __repr__(self) -> str:
        return (
            f"<Job(id={self.id}, title={self.title!r}, "
            f"company={self.company!r}, source={self.source!r})>"
        )


# ── Company ──────────────────────────────────────────────────────────────────


class Company(Base):
    """A company that may have direct ATS API integration.

    Attributes:
        id: Primary key.
        name: Company name (unique).
        website: Company website URL.
        greenhouse_token: Greenhouse ATS API token.
        lever_token: Lever ATS API token.
        ashby_token: Ashby ATS API token.
        is_active: Whether to actively scrape this company.
    """

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(unique=True, nullable=False)
    website: Mapped[Optional[str]] = mapped_column(default=None)
    greenhouse_token: Mapped[Optional[str]] = mapped_column(default=None)
    lever_token: Mapped[Optional[str]] = mapped_column(default=None)
    ashby_token: Mapped[Optional[str]] = mapped_column(default=None)
    is_active: Mapped[bool] = mapped_column(default=True)

    def __repr__(self) -> str:
        return f"<Company(id={self.id}, name={self.name!r})>"


# ── Application ──────────────────────────────────────────────────────────────


class Application(Base):
    """Tracks the status of a job application.

    Attributes:
        id: Primary key.
        job_id: Foreign key to :class:`Job`.
        status: Current application status (pending, applied, rejected, etc.).
        applied_at: Timestamp when the application was submitted.
        resume_path: Path to the resume used for this application.
        cover_letter_path: Path to the cover letter generated/used.
        notes: Free-text notes about the application.
        updated_at: Last update timestamp.
        job: Related :class:`Job` instance.
    """

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    status: Mapped[str] = mapped_column(default="pending")
    applied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=None
    )
    resume_path: Mapped[Optional[str]] = mapped_column(default=None)
    cover_letter_path: Mapped[Optional[str]] = mapped_column(default=None)
    notes: Mapped[Optional[str]] = mapped_column(Text, default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    job: Mapped["Job"] = relationship(back_populates="applications")

    def __repr__(self) -> str:
        return (
            f"<Application(id={self.id}, job_id={self.job_id}, "
            f"status={self.status!r})>"
        )


# ── Resume ───────────────────────────────────────────────────────────────────


class Resume(Base):
    """A stored resume document with optional parsed data.

    Attributes:
        id: Primary key.
        name: Human-readable name for this resume variant.
        file_path: Filesystem path to the resume file.
        parsed_data: JSON string of parsed resume contents.
        is_primary: Whether this is the default resume.
        created_at: When the resume was added.
    """

    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(nullable=False)
    file_path: Mapped[str] = mapped_column(nullable=False)
    parsed_data: Mapped[Optional[str]] = mapped_column(Text, default=None)
    is_primary: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<Resume(id={self.id}, name={self.name!r}, "
            f"is_primary={self.is_primary})>"
        )


# ── Log ──────────────────────────────────────────────────────────────────────


class Log(Base):
    """Application event log entry for auditing and debugging.

    Attributes:
        id: Primary key.
        event: Event type / category.
        source: Module or subsystem that generated the event.
        message: Detailed event message.
        created_at: When the event occurred.
    """

    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event: Mapped[str] = mapped_column(nullable=False)
    source: Mapped[Optional[str]] = mapped_column(default=None)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<Log(id={self.id}, event={self.event!r}, "
            f"source={self.source!r})>"
        )


# ── Table Creation Helper ────────────────────────────────────────────────────


def init_db() -> None:
    """Create all database tables defined by :class:`Base`.

    Uses the engine configured in :mod:`app.database.engine`.
    Safe to call multiple times — existing tables are not recreated.
    """
    from app.database.engine import engine as _engine

    Base.metadata.create_all(bind=_engine)
