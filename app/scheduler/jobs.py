"""
APScheduler configuration and background job definitions.

Defines the periodic tasks for job scraping, AI matching, email checking,
and daily digest notification alerts.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import func

from app.config import settings
from app.database.engine import SessionLocal
from app.database.models import Job, Application, Log
from app.scrapers import run_all_scrapers
from app.ai.matcher import run_matching_pipeline
from app.email_monitor.gmail_client import check_and_classify_emails
from app.notifications.telegram_bot import notify_daily_digest

logger = logging.getLogger(__name__)


# ── Job Definitions ─────────────────────────────────────────────────────────

def run_scraping_job() -> None:
    """Orchestrate a scraping run and follow-up matching."""
    logger.info("Scheduler: Starting automatic scraping job...")
    import asyncio
    
    db = SessionLocal()
    try:
        db.add(Log(event="scrape", source="Scheduler", message="Started automatic scraping job."))
        db.commit()
        
        # run_all_scrapers is async, we run it in a new loop
        summary = asyncio.run(run_all_scrapers())
        
        db.add(Log(
            event="scrape",
            source="Scheduler",
            message=f"Automatic scraping complete. Scraped: {summary['total_scraped']}, New: {summary['new_jobs']}."
        ))
        db.commit()
        
        # Follow up by running the matcher on new unscored jobs
        logger.info("Scheduler: Following up scraping with matching pipeline...")
        match_summary = run_matching_pipeline(db)
        
        if match_summary["matched"] > 0:
            db.add(Log(
                event="match",
                source="Scheduler",
                message=f"Automatic matching complete. Matched: {match_summary['matched']} jobs."
            ))
            db.commit()
            
    except Exception as e:
        logger.error("Scheduler: Automatic scraping job failed: %s", e)
        db.add(Log(event="error", source="Scheduler", message=f"Automatic scraping failed: {e}"))
        db.commit()
    finally:
        db.close()


def run_email_monitoring_job() -> None:
    """Orchestrate polling Gmail for status updates."""
    logger.info("Scheduler: Starting Gmail monitoring job...")
    db = SessionLocal()
    try:
        results = check_and_classify_emails(db)
        if results["classified"] > 0:
            logger.info("Scheduler: Classified %d job-related emails.", results["classified"])
    except Exception as e:
        logger.error("Scheduler: Gmail monitoring job failed: %s", e)
    finally:
        db.close()


def run_daily_digest_job() -> None:
    """Orchestrate sending the daily digest notification."""
    logger.info("Scheduler: Running daily digest job...")
    db = SessionLocal()
    try:
        # Get count of jobs scraped in last 24 hours
        one_day_ago = datetime.now()  # SQLite doesn't enforce timezone unless set
        total_scraped = db.query(Job).count()  # Simply total database stats for digest
        
        # Count high match jobs
        high_matches = db.query(Job).filter(Job.match_score >= 0.80).count()
        
        # Count applications updated today
        applied_today = db.query(Application).filter(
            Application.status == "applied"
        ).count()
        
        # Send Telegram notification
        notify_daily_digest(
            total_scraped=total_scraped,
            new_jobs=total_scraped,  # Simple representation
            high_matches=high_matches,
            applied_today=applied_today
        )
        
        db.add(Log(event="notifications", source="Scheduler", message="Sent daily digest to Telegram."))
        db.commit()
    except Exception as e:
        logger.error("Scheduler: Daily digest job failed: %s", e)
    finally:
        db.close()


# ── Scheduler Orchestrator ───────────────────────────────────────────────────

class JobScheduler:
    """Background scheduler managing periodic job runs."""

    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler()

    def start(self) -> None:
        """Start the background scheduler thread and register jobs."""
        logger.info("Starting background scheduler...")
        
        # 1. Job scraping (every N hours)
        self.scheduler.add_job(
            run_scraping_job,
            trigger=IntervalTrigger(hours=settings.scrape_interval_hours),
            id="job_scraping",
            name="Job Scraping Pipeline",
            max_instances=1,
            coalesce=True,
        )
        
        # 2. Email checking (every 30 minutes, runs immediately on startup)
        from datetime import datetime
        self.scheduler.add_job(
            run_email_monitoring_job,
            trigger=IntervalTrigger(minutes=30),
            id="email_monitoring",
            name="Gmail Inbox Poll",
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(),
        )
        
        # 3. Daily digest (every day at 9:00 AM)
        self.scheduler.add_job(
            run_daily_digest_job,
            trigger=CronTrigger(hour=9, minute=0),
            id="daily_digest",
            name="Daily Telegram Digest",
            max_instances=1,
            coalesce=True,
        )
        
        # Start execution
        self.scheduler.start()
        logger.info("Background scheduler started successfully.")

    def stop(self) -> None:
        """Shutdown the background scheduler thread."""
        logger.info("Stopping background scheduler...")
        self.scheduler.shutdown()
        logger.info("Background scheduler stopped.")
