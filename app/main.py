"""
Job Bot CLI — the main entry-point for the application.

Provides Click commands for database initialization, scraping,
AI matching, resume parsing, dashboard launching, and scheduling.

Usage::

    $ job-bot init-db
    $ job-bot scrape
    $ job-bot match
    $ job-bot parse-resume --path resume.pdf
    $ job-bot dashboard
    $ job-bot apply 42
    $ job-bot scheduler
    $ job-bot full
"""

from __future__ import annotations

import click
from rich.console import Console

console = Console()


@click.group()
def cli() -> None:
    """Job Bot — AI-powered job hunting agent."""


@cli.command("init-db")
def init_db_command() -> None:
    """Initialize the database, create required directories, and seed starter companies."""
    from app.config import settings
    from app.database.models import init_db, Company
    from app.database.engine import SessionLocal

    console.print("[bold blue]* Initialising database...[/bold blue]")
    settings.ensure_dirs()
    init_db()
    
    # Seed popular companies
    starter_companies = [
        # Greenhouse companies
        {"name": "Stripe", "greenhouse_token": "stripe", "website": "https://stripe.com"},
        {"name": "Figma", "greenhouse_token": "figma", "website": "https://figma.com"},
        {"name": "Notion", "greenhouse_token": "notion", "website": "https://notion.so"},
        {"name": "Reddit", "greenhouse_token": "reddit", "website": "https://reddit.com"},
        {"name": "Airbnb", "greenhouse_token": "airbnb", "website": "https://airbnb.com"},
        {"name": "Vercel", "greenhouse_token": "vercel", "website": "https://vercel.com"},
        {"name": "Cloudflare", "greenhouse_token": "cloudflare", "website": "https://cloudflare.com"},
        
        # Lever companies
        {"name": "Palantir", "lever_token": "palantir", "website": "https://palantir.com"},
        
        # Ashby companies
        {"name": "Sentry", "ashby_token": "sentry", "website": "https://sentry.io"},
        {"name": "Linear", "ashby_token": "linear", "website": "https://linear.app"},
        {"name": "Runway", "ashby_token": "runway", "website": "https://runwayml.com"},
        {"name": "Replit", "ashby_token": "replit", "website": "https://replit.com"},
        {"name": "Clerk", "ashby_token": "clerk", "website": "https://clerk.com"},
    ]
    
    db = SessionLocal()
    try:
        seeded_count = 0
        for comp_data in starter_companies:
            exists = db.query(Company).filter(Company.name == comp_data["name"]).first()
            if not exists:
                company = Company(
                    name=comp_data["name"],
                    website=comp_data.get("website"),
                    greenhouse_token=comp_data.get("greenhouse_token"),
                    lever_token=comp_data.get("lever_token"),
                    ashby_token=comp_data.get("ashby_token"),
                )
                db.add(company)
                seeded_count += 1
        db.commit()
        console.print(f"[bold green][OK] Seeded {seeded_count} starter companies.[/bold green]")
    except Exception as e:
        db.rollback()
        console.print(f"[bold red][ERROR] Failed to seed companies: {e}[/bold red]")
    finally:
        db.close()

    console.print("[bold green][OK] Database tables created.[/bold green]")
    console.print("[bold green][OK] Data directories ensured.[/bold green]")
    console.print(f"   Database URL : [cyan]{settings.database_url}[/cyan]")
    console.print(f"   Data dir     : [cyan]{settings.data_dir}[/cyan]")
    console.print(f"   Resumes dir  : [cyan]{settings.resumes_dir}[/cyan]")
    console.print(f"   Cover letters: [cyan]{settings.cover_letters_dir}[/cyan]")


@cli.command("scrape")
def scrape_command() -> None:
    """Run all configured job scrapers."""
    import asyncio
    from app.scrapers import run_all_scrapers
    
    console.print("[bold blue]* Starting job scraping pipeline...[/bold blue]")
    try:
        summary = asyncio.run(run_all_scrapers())
        console.print("\n[bold green][OK] Scraping Complete Summary:[/bold green]")
        console.print(f"  Total Scraped : [bold cyan]{summary['total_scraped']}[/bold cyan]")
        console.print(f"  New Jobs      : [bold green]{summary['new_jobs']}[/bold green]")
        console.print(f"  Duplicates    : [bold yellow]{summary['duplicates']}[/bold yellow]")
        console.print("\n[bold]Breakdown by source:[/bold]")
        for source, details in summary["per_source"].items():
            scraped = details.get("scraped", 0)
            err = details.get("error")
            if err:
                console.print(f"  - {source}: [red]Error ({err})[/red]")
            else:
                console.print(f"  - {source}: [cyan]{scraped} found[/cyan]")
    except Exception as e:
        console.print(f"[bold red][ERROR] Scraping failed: {e}[/bold red]")


@cli.command("match")
def match_command() -> None:
    """Run AI-powered job matching against your resume."""
    from app.database.engine import SessionLocal
    from app.ai.matcher import run_matching_pipeline
    
    console.print("[bold blue]* Starting job matching pipeline...[/bold blue]")
    db = SessionLocal()
    try:
        results = run_matching_pipeline(db)
        console.print(f"  Processed : [cyan]{results['processed']}[/cyan]")
        console.print(f"  Matched   : [green]{results['matched']}[/green]")
        console.print(f"  Failed    : [red]{results['failed']}[/red]")
    except Exception as e:
        console.print(f"[bold red][ERROR] Matching failed: {e}[/bold red]")
    finally:
        db.close()


@cli.command("parse-resume")
@click.option(
    "--path",
    required=True,
    type=click.Path(exists=True),
    help="Path to the resume PDF file.",
)
def parse_resume_command(path: str) -> None:
    """Parse a resume PDF and extract structured data."""
    import shutil
    from pathlib import Path
    from app.config import settings
    from app.database.engine import SessionLocal
    from app.database.models import Resume
    from app.ai.resume_parser import parse_resume
    
    console.print(f"[bold blue]* Parsing resume: {path}...[/bold blue]")
    try:
        # 1. Parse using AI
        parsed_data = parse_resume(path)
        
        # 2. Ensure resumes directory exists and copy the file
        settings.ensure_dirs()
        src_path = Path(path)
        dest_filename = f"resume_{src_path.name}"
        dest_path = settings.resumes_dir / dest_filename
        
        shutil.copy2(src_path, dest_path)
        console.print(f"  Copied resume to: [cyan]{dest_path}[/cyan]")
        
        # 3. Save to database
        db = SessionLocal()
        try:
            # Set any existing primary resumes to is_primary = False
            db.query(Resume).filter(Resume.is_primary == True).update({"is_primary": False})
            
            resume = Resume(
                name=src_path.stem,
                file_path=str(dest_path),
                parsed_data=parsed_data.model_dump_json(),
                is_primary=True
            )
            db.add(resume)
            db.commit()
            console.print("[bold green][OK] Resume successfully parsed and set as primary.[/bold green]")
            console.print(f"  Candidate Name: [bold cyan]{parsed_data.name}[/bold cyan]")
            console.print(f"  Skills Found  : [cyan]{len(parsed_data.skills)}[/cyan]")
            console.print(f"  Work Roles    : [cyan]{len(parsed_data.experience)}[/cyan]")
        except Exception as db_err:
            db.rollback()
            console.print(f"[bold red][ERROR] Database error: {db_err}[/bold red]")
        finally:
            db.close()
            
    except Exception as e:
        console.print(f"[bold red][ERROR] Parsing failed: {e}[/bold red]")


@cli.command("dashboard")
def dashboard_command() -> None:
    """Start the web dashboard using Uvicorn."""
    import uvicorn
    from app.config import settings

    console.print(f"[bold blue]* Starting web dashboard on {settings.dashboard_host}:{settings.dashboard_port}...[/bold blue]")
    uvicorn.run(
        "app.dashboard.api:app",
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        reload=True,
    )


@cli.command("apply")
@click.argument("job_id", type=int)
def apply_command(job_id: int) -> None:
    """Launch the interactive application assistant for a specific job."""
    import json
    from app.database.engine import SessionLocal
    from app.database.models import Job, Resume, Application
    from app.applicator.browser import launch_application_assistant

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            console.print(f"[bold red][ERROR] Job ID {job_id} not found in database.[/bold red]")
            return

        resume = db.query(Resume).filter(Resume.is_primary == True).first()
        if not resume or not resume.parsed_data:
            console.print("[bold red][ERROR] No primary parsed resume found. Please upload/parse a resume first.[/bold red]")
            return

        parsed_resume = json.loads(resume.parsed_data)
        name = parsed_resume.get("name", "Unknown Candidate")
        email = parsed_resume.get("email", "candidate@example.com")
        phone = parsed_resume.get("phone")

        console.print(f"[bold blue]* Launching application assistant for {job.title} at {job.company}...[/bold blue]")
        
        # Check if there is a tailored resume for this job
        app_record = db.query(Application).filter(Application.job_id == job_id).first()
        tailored_resume_path = None
        if app_record and app_record.resume_path:
            tailored_resume_path = app_record.resume_path
            console.print(f"  Using tailored resume: [cyan]{tailored_resume_path}[/cyan]")
        else:
            tailored_resume_path = resume.file_path
            console.print(f"  Using original resume: [cyan]{tailored_resume_path}[/cyan]")

        launch_application_assistant(
            url=job.url,
            name=name,
            email=email,
            phone=phone,
            resume_path=tailored_resume_path
        )
    except Exception as e:
        console.print(f"[bold red][ERROR] Failed to run application assistant: {e}[/bold red]")
    finally:
        db.close()


@cli.command("scheduler")
def scheduler_command() -> None:
    """Start the background APScheduler thread."""
    import time
    from app.scheduler.jobs import JobScheduler
    
    console.print("[bold blue]* Starting background scheduler thread...[/bold blue]")
    scheduler = JobScheduler()
    try:
        scheduler.start()
        console.print("[bold green][OK] Scheduler is running. Press Ctrl+C to stop.[/bold green]")
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.stop()
        console.print("[bold yellow]Scheduler stopped.[/bold yellow]")


@cli.command("full")
def full_command() -> None:
    """Start both the background scheduler and the web dashboard together."""
    import uvicorn
    from app.config import settings
    from app.scheduler.jobs import JobScheduler

    console.print("[bold blue]* Starting full system (Scheduler + Dashboard)...[/bold blue]")
    
    # Start scheduler in background
    scheduler = JobScheduler()
    scheduler.start()
    
    try:
        # Run dashboard in main thread (blocks until stopped)
        uvicorn.run(
            "app.dashboard.api:app",
            host=settings.dashboard_host,
            port=settings.dashboard_port,
            reload=False,  # reload must be false when running with background threads
        )
    finally:
        scheduler.stop()


if __name__ == "__main__":
    cli()
