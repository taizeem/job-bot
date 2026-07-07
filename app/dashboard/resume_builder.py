"""
Resume Builder API routes.

Provides endpoints for building a resume profile directly on the dashboard,
managing experience/education/projects/certifications, and downloading a PDF.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.database.models import (
    UserProfile,
    UserExperience,
    UserEducation,
    UserProject,
    UserCertification,
)

logger = logging.getLogger(__name__)

resume_router = APIRouter()

# Templates are loaded from the same directory as api.py
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ── Helpers ──────────────────────────────────────────────────────────────────


def _profile_to_dict(profile: UserProfile) -> dict:
    """Serialize a UserProfile and its related entries to a dict."""
    return {
        "id": profile.id,
        "name": profile.name,
        "email": profile.email,
        "phone": profile.phone,
        "location": profile.location,
        "country": profile.country,
        "summary": profile.summary,
        "skills": json.loads(profile.skills) if profile.skills else [],
        "preferred_job_titles": json.loads(profile.preferred_job_titles)
        if profile.preferred_job_titles
        else [],
        "preferred_locations": json.loads(profile.preferred_locations)
        if profile.preferred_locations
        else [],
        "experience": [
            {
                "id": exp.id,
                "company": exp.company,
                "title": exp.title,
                "start_date": exp.start_date,
                "end_date": exp.end_date,
                "is_current": exp.is_current,
                "bullets": json.loads(exp.bullets) if exp.bullets else [],
            }
            for exp in profile.experiences
        ],
        "education": [
            {
                "id": edu.id,
                "institution": edu.institution,
                "degree": edu.degree,
                "field": edu.field,
                "year": edu.year,
            }
            for edu in profile.education
        ],
        "projects": [
            {
                "id": proj.id,
                "name": proj.name,
                "description": proj.description,
                "technologies": json.loads(proj.technologies)
                if proj.technologies
                else [],
            }
            for proj in profile.projects
        ],
        "certifications": [
            {"id": cert.id, "name": cert.name} for cert in profile.certifications
        ],
    }


def _get_or_create_profile(db: Session) -> UserProfile:
    """Return the first UserProfile, creating one if none exists."""
    profile = db.query(UserProfile).first()
    if not profile:
        profile = UserProfile(name="")
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


# ── Page Route ───────────────────────────────────────────────────────────────


@resume_router.get("/resume", response_class=HTMLResponse)
async def resume_builder_page(request: Request, db: Session = Depends(get_db)):
    """Render the resume builder page."""
    profile = db.query(UserProfile).first()
    profile_data = _profile_to_dict(profile) if profile else None
    return templates.TemplateResponse(
        request,
        "resume_builder.html",
        {"profile": profile_data},
    )


# ── API: Profile ─────────────────────────────────────────────────────────────


@resume_router.get("/api/profile")
async def get_profile(db: Session = Depends(get_db)):
    """Fetch the current user profile with all sections."""
    profile = db.query(UserProfile).first()
    if not profile:
        return {"profile": None}
    return {"profile": _profile_to_dict(profile)}


@resume_router.post("/api/profile")
async def save_profile(request: Request, db: Session = Depends(get_db)):
    """Create or update the user profile (personal info, skills, preferences)."""
    body = await request.json()

    profile = _get_or_create_profile(db)

    # Update fields
    profile.name = body.get("name", profile.name)
    profile.email = body.get("email", profile.email)
    profile.phone = body.get("phone", profile.phone)
    profile.location = body.get("location", profile.location)
    profile.country = body.get("country", profile.country)
    profile.summary = body.get("summary", profile.summary)

    # JSON list fields
    if "skills" in body:
        profile.skills = json.dumps(body["skills"]) if body["skills"] else None
    if "preferred_job_titles" in body:
        profile.preferred_job_titles = (
            json.dumps(body["preferred_job_titles"])
            if body["preferred_job_titles"]
            else None
        )
    if "preferred_locations" in body:
        profile.preferred_locations = (
            json.dumps(body["preferred_locations"])
            if body["preferred_locations"]
            else None
        )

    db.commit()
    db.refresh(profile)

    return {"status": "success", "profile": _profile_to_dict(profile)}


# ── API: Experience ──────────────────────────────────────────────────────────


@resume_router.post("/api/profile/experience")
async def save_experience(request: Request, db: Session = Depends(get_db)):
    """Add or update a work experience entry."""
    body = await request.json()
    profile = _get_or_create_profile(db)

    exp_id = body.get("id")
    if exp_id:
        exp = db.query(UserExperience).filter(UserExperience.id == exp_id).first()
        if not exp or exp.profile_id != profile.id:
            raise HTTPException(404, "Experience entry not found")
    else:
        exp = UserExperience(profile_id=profile.id)
        db.add(exp)

    exp.company = body.get("company", "")
    exp.title = body.get("title", "")
    exp.start_date = body.get("start_date")
    exp.end_date = body.get("end_date")
    exp.is_current = body.get("is_current", False)
    exp.bullets = json.dumps(body.get("bullets", []))

    db.commit()
    return {"status": "success", "id": exp.id}


@resume_router.delete("/api/profile/experience/{exp_id}")
async def delete_experience(exp_id: int, db: Session = Depends(get_db)):
    """Remove a work experience entry."""
    exp = db.query(UserExperience).filter(UserExperience.id == exp_id).first()
    if not exp:
        raise HTTPException(404, "Experience entry not found")
    db.delete(exp)
    db.commit()
    return {"status": "success"}


# ── API: Education ───────────────────────────────────────────────────────────


@resume_router.post("/api/profile/education")
async def save_education(request: Request, db: Session = Depends(get_db)):
    """Add or update an education entry."""
    body = await request.json()
    profile = _get_or_create_profile(db)

    edu_id = body.get("id")
    if edu_id:
        edu = db.query(UserEducation).filter(UserEducation.id == edu_id).first()
        if not edu or edu.profile_id != profile.id:
            raise HTTPException(404, "Education entry not found")
    else:
        edu = UserEducation(profile_id=profile.id)
        db.add(edu)

    edu.institution = body.get("institution", "")
    edu.degree = body.get("degree")
    edu.field = body.get("field")
    edu.year = body.get("year")

    db.commit()
    return {"status": "success", "id": edu.id}


@resume_router.delete("/api/profile/education/{edu_id}")
async def delete_education(edu_id: int, db: Session = Depends(get_db)):
    """Remove an education entry."""
    edu = db.query(UserEducation).filter(UserEducation.id == edu_id).first()
    if not edu:
        raise HTTPException(404, "Education entry not found")
    db.delete(edu)
    db.commit()
    return {"status": "success"}


# ── API: Projects ────────────────────────────────────────────────────────────


@resume_router.post("/api/profile/project")
async def save_project(request: Request, db: Session = Depends(get_db)):
    """Add or update a project entry."""
    body = await request.json()
    profile = _get_or_create_profile(db)

    proj_id = body.get("id")
    if proj_id:
        proj = db.query(UserProject).filter(UserProject.id == proj_id).first()
        if not proj or proj.profile_id != profile.id:
            raise HTTPException(404, "Project not found")
    else:
        proj = UserProject(profile_id=profile.id)
        db.add(proj)

    proj.name = body.get("name", "")
    proj.description = body.get("description")
    proj.technologies = json.dumps(body.get("technologies", []))

    db.commit()
    return {"status": "success", "id": proj.id}


@resume_router.delete("/api/profile/project/{proj_id}")
async def delete_project(proj_id: int, db: Session = Depends(get_db)):
    """Remove a project entry."""
    proj = db.query(UserProject).filter(UserProject.id == proj_id).first()
    if not proj:
        raise HTTPException(404, "Project not found")
    db.delete(proj)
    db.commit()
    return {"status": "success"}


# ── API: Certifications ──────────────────────────────────────────────────────


@resume_router.post("/api/profile/certification")
async def save_certification(request: Request, db: Session = Depends(get_db)):
    """Add or update a certification."""
    body = await request.json()
    profile = _get_or_create_profile(db)

    cert_id = body.get("id")
    if cert_id:
        cert = (
            db.query(UserCertification)
            .filter(UserCertification.id == cert_id)
            .first()
        )
        if not cert or cert.profile_id != profile.id:
            raise HTTPException(404, "Certification not found")
    else:
        cert = UserCertification(profile_id=profile.id)
        db.add(cert)

    cert.name = body.get("name", "")

    db.commit()
    return {"status": "success", "id": cert.id}


@resume_router.delete("/api/profile/certification/{cert_id}")
async def delete_certification(cert_id: int, db: Session = Depends(get_db)):
    """Remove a certification."""
    cert = (
        db.query(UserCertification)
        .filter(UserCertification.id == cert_id)
        .first()
    )
    if not cert:
        raise HTTPException(404, "Certification not found")
    db.delete(cert)
    db.commit()
    return {"status": "success"}


# ── API: PDF Download ────────────────────────────────────────────────────────


@resume_router.get("/api/profile/download-pdf")
async def download_resume_pdf(db: Session = Depends(get_db)):
    """Generate and stream the resume as a PDF file."""
    profile = db.query(UserProfile).first()
    if not profile or not profile.name:
        raise HTTPException(400, "No profile found. Please build your resume first.")

    from app.ai.pdf_generator import generate_resume_pdf

    profile_data = _profile_to_dict(profile)
    pdf_bytes = generate_resume_pdf(profile_data)

    safe_name = "".join(
        c for c in profile.name if c.isalnum() or c in (" ", "-", "_")
    ).strip()
    filename = f"{safe_name}_Resume.pdf" if safe_name else "Resume.pdf"

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
