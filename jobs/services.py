import logging
from typing import Dict, List, Optional
from django.utils import timezone
from .automation import JobApplicationBot
from .matching import AIMatchingEngine
from .models import Application, ApplicationLog, JobListing, Resume

logger = logging.getLogger(__name__)


class JobApplicationPipeline:
    """Orchestrates candidate evaluation, decision logic, and automated job submissions."""

    def __init__(self, match_threshold: float = 75.0, headless: bool = True):
        self.match_threshold = match_threshold
        self.headless = headless
        self.matching_engine = AIMatchingEngine()
        self.bot = JobApplicationBot(headless=headless)

    def run_for_resume(
        self,
        resume: Resume,
        job_limit: int = 10,
        dry_run: bool = False,
    ) -> List[Dict[str, any]]:
        """
        Executes matching and auto-apply for all unapplied jobs against a given resume.
        """
        results: List[Dict[str, any]] = []

        # Find jobs that have not been applied to by this resume
        applied_job_ids = Application.objects.filter(resume=resume).values_list("job_id", flat=True)
        available_jobs = JobListing.objects.exclude(id__in=applied_job_ids)[:job_limit]

        if not available_jobs.exists():
            logger.info("No new unapplied job listings found.")
            return results

        candidate_name = resume.name or "Applicant"
        candidate_email = resume.metadata.get("email", "candidate@example.com")
        candidate_phone = resume.metadata.get("phone", "+15551234567")
        resume_path = resume.file.path if resume.file else None

        for job in available_jobs:
            logger.info(f"Evaluating: {job.title} at {job.company}")

            # 1. AI Matching
            match_data = self.matching_engine.evaluate_fit(
                resume_text=resume.parsed_text,
                resume_skills=resume.extracted_skills,
                job_title=job.title,
                job_description=job.description,
                required_skills=job.required_skills,
            )
            score = match_data["match_score"]
            cover_letter = match_data["cover_letter"]
            summary = match_data["summary"]

            # 2. Create Application record
            application, _ = Application.objects.get_or_create(
                resume=resume,
                job=job,
                defaults={
                    "match_score": score,
                    "status": Application.STATUS_PENDING,
                    "cover_letter": cover_letter,
                    "notes": summary,
                },
            )

            ApplicationLog.objects.create(
                application=application,
                level=ApplicationLog.LEVEL_INFO,
                message=f"Match evaluation complete. Score: {score}%. Summary: {summary}",
            )

            # 3. Decision Logic: Apply if score meets threshold
            if score >= self.match_threshold:
                if dry_run:
                    ApplicationLog.objects.create(
                        application=application,
                        level=ApplicationLog.LEVEL_INFO,
                        message=f"[DRY RUN] Score {score}% meets threshold {self.match_threshold}%. Submission skipped.",
                    )
                    results.append({"job": job.title, "score": score, "applied": False, "dry_run": True})
                    continue

                ApplicationLog.objects.create(
                    application=application,
                    level=ApplicationLog.LEVEL_INFO,
                    message=f"Score {score}% meets threshold {self.match_threshold}%. Initiating browser auto-apply bot.",
                )

                screenshot_name = f"app_{application.id}_{job.id}.png"
                bot_result = self.bot.submit_application(
                    job_url=job.url,
                    candidate_name=candidate_name,
                    candidate_email=candidate_email,
                    candidate_phone=candidate_phone,
                    resume_path=resume_path,
                    cover_letter=cover_letter,
                    screenshot_name=screenshot_name,
                )

                if bot_result["success"]:
                    application.status = Application.STATUS_APPLIED
                    application.applied_at = timezone.now()
                    application.save()

                    ApplicationLog.objects.create(
                        application=application,
                        level=ApplicationLog.LEVEL_INFO,
                        message=f"Auto-applied successfully. Details: {bot_result['message']}",
                    )
                    results.append({"job": job.title, "score": score, "applied": True})
                else:
                    ApplicationLog.objects.create(
                        application=application,
                        level=ApplicationLog.LEVEL_ERROR,
                        message=f"Auto-apply failed: {bot_result['message']}",
                    )
                    results.append({"job": job.title, "score": score, "applied": False, "error": bot_result["message"]})
            else:
                ApplicationLog.objects.create(
                    application=application,
                    level=ApplicationLog.LEVEL_WARNING,
                    message=f"Score {score}% is below threshold {self.match_threshold}%. Marked as Pending / Skipped.",
                )
                results.append({"job": job.title, "score": score, "applied": False})

        return results