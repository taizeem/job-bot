import logging
from typing import Any, Dict, List, Optional
from django.conf import settings
from django.utils import timezone
from .automation import JobApplicationBot
from .matching import AIMatchingEngine
from .models import Application, ApplicationLog, JobListing, Resume

logger = logging.getLogger(__name__)


class JobApplicationPipeline:
    """Orchestrates multi-resume routing, review gating, pacing limits, and submissions."""

    def __init__(self, headless: bool = True):
        self.auto_apply_threshold: float = getattr(settings, "AUTO_APPLY_THRESHOLD", 80.0)
        self.review_threshold: float = getattr(settings, "REVIEW_THRESHOLD", 65.0)
        self.daily_limit: int = getattr(settings, "DAILY_APPLICATION_LIMIT", 10)
        self.headless = headless
        self.matching_engine = AIMatchingEngine()
        self.bot = JobApplicationBot(headless=headless)

    def get_todays_applied_count(self) -> int:
        """Returns the number of applications submitted today."""
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return Application.objects.filter(
            status=Application.STATUS_APPLIED,
            applied_at__gte=today_start,
        ).count()

    def run_pipeline(self, job_limit: int = 10, dry_run: bool = False) -> List[Dict[str, Any]]:
        """
        Evaluates jobs against all resumes, selects the best resume per job,
        enforces pacing caps, and routes to Auto-Apply or Needs Review.
        """
        results: List[Dict[str, Any]] = []
        all_resumes = list(Resume.objects.all())

        if not all_resumes:
            logger.warning("No resumes found. Please upload at least one resume.")
            return results

        # Find unapplied jobs
        applied_job_ids = Application.objects.filter(
            status__in=[Application.STATUS_APPLIED, Application.STATUS_INTERVIEW]
        ).values_list("job_id", flat=True)
        available_jobs = JobListing.objects.exclude(id__in=applied_job_ids)[:job_limit]

        today_applied = self.get_todays_applied_count()

        for job in available_jobs:
            # 1. Multi-Resume Routing: Match job against ALL resumes and pick highest score
            best_resume: Optional[Resume] = None
            best_score: float = -1.0
            best_data: Dict[str, Any] = {}

            for resume in all_resumes:
                eval_data = self.matching_engine.evaluate_fit(
                    resume_text=resume.parsed_text,
                    resume_skills=resume.extracted_skills,
                    job_title=job.title,
                    job_description=job.description,
                    required_skills=job.required_skills,
                )
                if eval_data["match_score"] > best_score:
                    best_score = eval_data["match_score"]
                    best_resume = resume
                    best_data = eval_data

            if not best_resume:
                continue

            # 2. Create or update the Application record
            application, _ = Application.objects.get_or_create(
                resume=best_resume,
                job=job,
                defaults={
                    "match_score": best_score,
                    "matching_skills": best_data.get("matching_skills", []),
                    "missing_skills": best_data.get("missing_skills", []),
                    "cover_letter": best_data.get("cover_letter", ""),
                    "notes": best_data.get("summary", ""),
                    "status": Application.STATUS_PENDING,
                },
            )

            ApplicationLog.objects.create(
                application=application,
                level=ApplicationLog.LEVEL_INFO,
                message=(
                    f"Multi-resume matched with '{best_resume.name}'. "
                    f"Score: {best_score}%. Summary: {best_data.get('summary', '')}"
                ),
            )

            # 3. Decision Logic: Auto-Apply vs Needs Review vs Pending
            if best_score >= self.auto_apply_threshold:
                # Check daily submission cap
                if today_applied >= self.daily_limit:
                    application.status = Application.STATUS_NEEDS_REVIEW
                    application.save()
                    ApplicationLog.objects.create(
                        application=application,
                        level=ApplicationLog.LEVEL_WARNING,
                        message=f"Daily limit of {self.daily_limit} reached. Application held in Needs Review queue.",
                    )
                    results.append({"job": job.title, "score": best_score, "status": "HELD_DAILY_LIMIT"})
                    continue

                if dry_run:
                    results.append({"job": job.title, "score": best_score, "status": "DRY_RUN"})
                    continue

                # Auto-apply
                submitted = self.apply_to_application(application)
                if submitted:
                    today_applied += 1
                    results.append({"job": job.title, "score": best_score, "status": "AUTO_APPLIED"})
                else:
                    results.append({"job": job.title, "score": best_score, "status": "FAILED"})

            elif best_score >= self.review_threshold:
                # Score between 65% and 79% goes to Human-in-the-Loop review gate
                application.status = Application.STATUS_NEEDS_REVIEW
                application.save()
                ApplicationLog.objects.create(
                    application=application,
                    level=ApplicationLog.LEVEL_INFO,
                    message=f"Score {best_score}% placed in 'Needs Review' queue for manual approval.",
                )
                results.append({"job": job.title, "score": best_score, "status": "NEEDS_REVIEW"})
            else:
                application.status = Application.STATUS_PENDING
                application.save()
                results.append({"job": job.title, "score": best_score, "status": "SKIPPED_LOW_SCORE"})

        return results

    def apply_to_application(self, application: Application) -> bool:
        """Executes browser automation for a specific application record."""
        resume = application.resume
        job = application.job

        candidate_name = resume.name or "Applicant"
        candidate_email = resume.metadata.get("email", "candidate@example.com")
        candidate_phone = resume.metadata.get("phone", "+15551234567")
        resume_path = resume.file.path if resume.file else None

        screenshot_name = f"app_{application.id}_{job.id}.png"
        bot_result = self.bot.submit_application(
            job_url=job.url,
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            candidate_phone=candidate_phone,
            resume_path=resume_path,
            cover_letter=application.cover_letter,
            screenshot_name=screenshot_name,
        )

        if bot_result["success"]:
            application.status = Application.STATUS_APPLIED
            application.applied_at = timezone.now()
            application.save()

            ApplicationLog.objects.create(
                application=application,
                level=ApplicationLog.LEVEL_INFO,
                message=f"Application submitted successfully via bot. Details: {bot_result['message']}",
            )
            return True
        else:
            ApplicationLog.objects.create(
                application=application,
                level=ApplicationLog.LEVEL_ERROR,
                message=f"Submission failed: {bot_result['message']}",
            )
            return False