"""
FastAPI application for the Job Bot Web Dashboard.

Provides routes for listing jobs, tracking applications, triggering scrapers,
running matches, and uploading resumes. Renders premium dark-themed templates.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Depends, Form, File, UploadFile, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.database.engine import get_db
from app.database.models import Job, Company, Application, Resume, Log
from app.scrapers import run_all_scrapers
from app.ai.matcher import run_matching_pipeline
from app.ai.resume_parser import parse_resume
from app.ai.resume_tailor import tailor_resume, save_tailored_resume
from app.ai.cover_letter import generate_cover_letter, save_cover_letter

logger = logging.getLogger(__name__)

app = FastAPI(title="Job Bot Dashboard")

# Resolve template & static directories relative to this file
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Ensure directories exist
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Mount static and templates
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ── Page Routes ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request, db: Session = Depends(get_db)):
    """Render the dashboard stats home page."""
    # Compute counts
    total_jobs = db.query(Job).count()
    applied_count = db.query(Application).filter(Application.status == "applied").count()
    interview_count = db.query(Application).filter(Application.status == "interview").count()
    rejected_count = db.query(Application).filter(Application.status == "rejected").count()
    offer_count = db.query(Application).filter(Application.status == "offer").count()
    
    # Recent logs
    recent_logs = db.query(Log).order_by(Log.created_at.desc()).limit(5).all()
    
    # High match jobs count (>= 80%)
    high_matches = db.query(Job).filter(Job.match_score >= 0.80).count()
    
    # Active companies
    active_companies = db.query(Company).filter(Company.is_active == True).count()
    
    # Check if primary resume is uploaded
    has_resume = db.query(Resume).filter(Resume.is_primary == True).first() is not None

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "total_jobs": total_jobs,
            "applied_count": applied_count,
            "interview_count": interview_count,
            "rejected_count": rejected_count,
            "offer_count": offer_count,
            "high_matches": high_matches,
            "active_companies": active_companies,
            "has_resume": has_resume,
            "recent_logs": recent_logs,
        }
    )


@app.get("/jobs", response_class=HTMLResponse)
async def jobs_page(
    request: Request,
    min_score: Optional[str] = None,
    remote_only: Optional[str] = None,
    query: Optional[str] = None,
    page: int = 1,
    db: Session = Depends(get_db)
):
    """Render job listings list with pagination and optional filters."""
    per_page = 50
    q = db.query(Job)
    
    # Safely parse min_score as an integer
    score_val = None
    if min_score and min_score.strip():
        try:
            score_val = int(min_score)
        except ValueError:
            try:
                score_val = int(float(min_score))
            except ValueError:
                pass

    if score_val is not None:
        q = q.filter(Job.match_score >= (score_val / 100.0))
        
    # Safely parse remote_only checkbox
    is_remote = False
    if remote_only and remote_only.lower() in ("true", "1", "on", "yes"):
        is_remote = True
        
    if is_remote:
        q = q.filter(Job.remote == True)
        
    if query:
        q = q.filter(
            Job.title.contains(query) | 
            Job.company.contains(query) | 
            Job.description.contains(query)
        )
        
    total_items = q.count()
    total_pages = (total_items + per_page - 1) // per_page
    
    # Restrict page bounds
    page = max(1, min(page, total_pages)) if total_pages > 0 else 1
    
    jobs = q.order_by(Job.match_score.desc().nullslast(), Job.scraped_at.desc())\
            .offset((page - 1) * per_page)\
            .limit(per_page)\
            .all()

    return templates.TemplateResponse(
        request,
        "jobs.html",
        {
            "jobs": jobs,
            "min_score": score_val,
            "remote_only": is_remote,
            "query": query,
            "page": page,
            "total_pages": total_pages,
            "total_items": total_items,
        }
    )


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail_page(request: Request, job_id: int, db: Session = Depends(get_db)):
    """Render details of a single job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    # Check if application exists
    app_record = db.query(Application).filter(Application.job_id == job_id).first()
    has_resume = db.query(Resume).filter(Resume.is_primary == True).first() is not None

    return templates.TemplateResponse(
        request,
        "job_detail.html",
        {
            "job": job,
            "application": app_record,
            "has_resume": has_resume,
        }
    )


@app.get("/applications", response_class=HTMLResponse)
async def applications_page(request: Request, db: Session = Depends(get_db)):
    """Render the application tracking board."""
    apps = db.query(Application).join(Job).order_by(Application.updated_at.desc()).all()
    return templates.TemplateResponse(request, "applications.html", {"applications": apps})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    """Render configuration and settings page."""
    companies = db.query(Company).all()
    primary_resume = db.query(Resume).filter(Resume.is_primary == True).first()
    
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "companies": companies,
            "resume": primary_resume,
            "ai_model": settings.ai_model,
            "telegram_bot_token": settings.telegram_bot_token,
            "telegram_chat_id": settings.telegram_chat_id,
        }
    )


# ── Action / API Routes ──────────────────────────────────────────────────────

from fastapi import BackgroundTasks

# Global matching task states
IS_MATCHING = False
LAST_MATCHED_COUNT = 0


def run_scrape_task():
    """Wrapper to run async scraping pipeline in a background thread."""
    import asyncio
    try:
        # Create a new event loop for the background thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_all_scrapers())
        loop.close()
    except Exception as e:
        logger.error("Background scrape task failed: %s", e)


def run_match_task():
    """Wrapper to run matching pipeline with a fresh DB session in background."""
    global IS_MATCHING, LAST_MATCHED_COUNT
    from app.database.engine import SessionLocal
    db = SessionLocal()
    try:
        summary = run_matching_pipeline(db)
        LAST_MATCHED_COUNT = summary.get("matched", 0)
    except Exception as e:
        logger.error("Background match task failed: %s", e)
        LAST_MATCHED_COUNT = 0
    finally:
        db.close()
        IS_MATCHING = False


@app.post("/api/scrape")
async def trigger_scrape(background_tasks: BackgroundTasks):
    """Trigger the background scraping pipeline and return immediately."""
    background_tasks.add_task(run_scrape_task)
    return {"status": "success", "message": "Job scraping started in the background."}


@app.post("/api/match")
async def trigger_matching(background_tasks: BackgroundTasks):
    """Trigger job matching on all unmatched jobs in the background."""
    global IS_MATCHING
    IS_MATCHING = True
    background_tasks.add_task(run_match_task)
    return {"status": "success", "message": "AI matching pipeline started in the background."}


@app.get("/api/match/status")
async def get_match_status():
    """Check progress of active AI matching task."""
    global IS_MATCHING, LAST_MATCHED_COUNT
    return {
        "status": "running" if IS_MATCHING else "idle",
        "matched_count": LAST_MATCHED_COUNT
    }


@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a new PDF resume, parse it, and set as primary."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    settings.ensure_dirs()
    temp_path = settings.resumes_dir / f"temp_{file.filename}"
    
    try:
        # Save temp file
        with open(temp_path, "wb") as f:
            f.write(await file.read())
            
        # Parse using resume parser
        parsed_data = parse_resume(temp_path)
        
        # Rename to final destination
        final_path = settings.resumes_dir / f"resume_{file.filename}"
        if temp_path.exists():
            temp_path.rename(final_path)
            
        # De-primary old resumes
        db.query(Resume).filter(Resume.is_primary == True).update({"is_primary": False})
        
        # Create DB record
        resume = Resume(
            name=Path(file.filename).stem,
            file_path=str(final_path),
            parsed_data=parsed_data.model_dump_json(),
            is_primary=True
        )
        db.add(resume)
        db.commit()
        
        return RedirectResponse(url="/settings", status_code=302)
        
    except Exception as e:
        logger.error("Failed to upload/parse resume: %s", e)
        if temp_path.exists():
            temp_path.unlink()
        raise HTTPException(status_code=500, detail=f"Parsing failed: {e}")


@app.post("/api/jobs/{job_id}/tailor")
async def tailor_job_materials(job_id: int, db: Session = Depends(get_db)):
    """Generate tailored resume and cover letter for a job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    resume = db.query(Resume).filter(Resume.is_primary == True).first()
    if not resume:
        raise HTTPException(status_code=400, detail="No primary resume found. Please upload one in settings.")
        
    try:
        # 1. Tailor Resume
        tailored_resume_md = tailor_resume(
            resume_json=resume.parsed_data,
            job_title=job.title,
            company_name=job.company,
            job_description=job.description
        )
        tailored_path = save_tailored_resume(job.id, job.company, tailored_resume_md)
        
        # 2. Cover Letter
        cover_letter_md = generate_cover_letter(
            resume_json=resume.parsed_data,
            job_title=job.title,
            company_name=job.company,
            job_description=job.description
        )
        cover_path = save_cover_letter(job.id, job.company, cover_letter_md)
        
        # 3. Create or update application record
        app_record = db.query(Application).filter(Application.job_id == job_id).first()
        if not app_record:
            app_record = Application(
                job_id=job.id,
                status="pending",
            )
            db.add(app_record)
            
        app_record.resume_path = str(tailored_path)
        app_record.cover_letter_path = str(cover_path)
        app_record.updated_at = func.now()
        db.commit()
        
        return {"status": "success", "resume_path": str(tailored_path), "cover_letter_path": str(cover_path)}
        
    except Exception as e:
        logger.error("Failed to generate tailored materials: %s", e)
        return {"status": "error", "message": str(e)}


@app.get("/api/download/resume/{job_id}")
async def download_tailored_resume(job_id: int, db: Session = Depends(get_db)):
    """Download the generated tailored resume Markdown file."""
    app_record = db.query(Application).filter(Application.job_id == job_id).first()
    if not app_record or not app_record.resume_path:
        raise HTTPException(status_code=404, detail="Tailored resume not found")
    return FileResponse(app_record.resume_path, filename=Path(app_record.resume_path).name)


@app.get("/api/download/cover-letter/{job_id}")
async def download_cover_letter(job_id: int, db: Session = Depends(get_db)):
    """Download the generated cover letter Markdown file."""
    app_record = db.query(Application).filter(Application.job_id == job_id).first()
    if not app_record or not app_record.cover_letter_path:
        raise HTTPException(status_code=404, detail="Cover letter not found")
    return FileResponse(app_record.cover_letter_path, filename=Path(app_record.cover_letter_path).name)


@app.post("/api/applications/{job_id}/status")
async def update_status(job_id: int, status: str = Form(...), db: Session = Depends(get_db)):
    """Update application tracking status."""
    app_record = db.query(Application).filter(Application.job_id == job_id).first()
    if not app_record:
        app_record = Application(job_id=job_id, status=status)
        db.add(app_record)
    else:
        app_record.status = status
        app_record.updated_at = func.now()
        
    if status == "applied" and not app_record.applied_at:
        app_record.applied_at = func.now()
        
    db.commit()
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=302)


@app.post("/api/companies/add")
async def add_company(
    name: str = Form(...),
    website: Optional[str] = Form(None),
    greenhouse_token: Optional[str] = Form(None),
    lever_token: Optional[str] = Form(None),
    ashby_token: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Add a new company to track / scrape."""
    try:
        company = Company(
            name=name,
            website=website,
            greenhouse_token=greenhouse_token or None,
            lever_token=lever_token or None,
            ashby_token=ashby_token or None,
        )
        db.add(company)
        db.commit()
        return RedirectResponse(url="/settings", status_code=302)
    except Exception as e:
        logger.error("Failed to add company: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
