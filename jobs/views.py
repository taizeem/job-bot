from collections import Counter
import logging
from django.conf import settings
from django.contrib import messages
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .fetcher import JobFetcherService
from .forms import ApplicationStatusUpdateForm, ResumeUploadForm
from .models import Application, ApplicationLog, JobListing, Resume
from .parsers import extract_text_from_pdf, parse_resume_metadata
from .services import JobApplicationPipeline

logger = logging.getLogger(__name__)


def dashboard_view(request):
    """Main dashboard displaying metrics, pure CSS funnel, skill gaps, and applications."""
    total_resumes = Resume.objects.count()
    total_jobs = JobListing.objects.count()
    total_applications = Application.objects.count()

    applied_count = Application.objects.filter(status=Application.STATUS_APPLIED).count()
    interview_count = Application.objects.filter(status=Application.STATUS_INTERVIEW).count()
    review_count = Application.objects.filter(status=Application.STATUS_NEEDS_REVIEW).count()
    rejected_count = Application.objects.filter(status=Application.STATUS_REJECTED).count()
    pending_count = Application.objects.filter(status=Application.STATUS_PENDING).count()

    avg_score_data = Application.objects.aggregate(avg=Avg("match_score"))
    avg_score = round(avg_score_data["avg"], 1) if avg_score_data.get("avg") is not None else 0.0

    # 1. Pacing Quota (pre-calculated to prevent template ZeroDivisionError)
    daily_limit = getattr(settings, "DAILY_APPLICATION_LIMIT", 10)
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_applied = Application.objects.filter(
        status=Application.STATUS_APPLIED,
        applied_at__gte=today_start,
    ).count()

    pacing_percentage = min(100, int((today_applied / daily_limit) * 100)) if daily_limit > 0 else 0

    # 2. Search & Filter
    status_filter = request.GET.get("status", "").strip()
    search_query = request.GET.get("q", "").strip()

    applications = Application.objects.select_related("job", "resume").all()

    if status_filter:
        applications = applications.filter(status=status_filter)

    if search_query:
        applications = applications.filter(
            Q(job__title__icontains=search_query)
            | Q(job__company__icontains=search_query)
            | Q(job__location__icontains=search_query)
        )

    # 3. Safe Skill Gap Extraction (never crashes on None or missing values)
    all_missing = []
    for app in Application.objects.only("missing_skills").all():
        skills = getattr(app, "missing_skills", None)
        if isinstance(skills, list):
            all_missing.extend(skills)

    top_skills_raw = Counter(all_missing).most_common(6)
    # Convert tuples to clean dictionary objects for 100% reliable template rendering
    top_missing_skills = [{"name": s[0], "count": s[1]} for s in top_skills_raw]

    # 4. Pure CSS Funnel Data (no external JS or Chart.js dependencies)
    max_count = max([total_applications, 1])
    funnel_data = [
        {
            "label": "Total Tracked",
            "count": total_applications,
            "bar_class": "bg-slate-700",
            "percentage": int((total_applications / max_count) * 100) if total_applications else 0,
        },
        {
            "label": "Needs Review",
            "count": review_count,
            "bar_class": "bg-amber-500",
            "percentage": int((review_count / max_count) * 100) if review_count else 0,
        },
        {
            "label": "Applied",
            "count": applied_count,
            "bar_class": "bg-sky-500",
            "percentage": int((applied_count / max_count) * 100) if applied_count else 0,
        },
        {
            "label": "Interview",
            "count": interview_count,
            "bar_class": "bg-purple-600",
            "percentage": int((interview_count / max_count) * 100) if interview_count else 0,
        },
        {
            "label": "Rejected",
            "count": rejected_count,
            "bar_class": "bg-rose-500",
            "percentage": int((rejected_count / max_count) * 100) if rejected_count else 0,
        },
    ]

    context = {
        "total_resumes": total_resumes,
        "total_jobs": total_jobs,
        "total_applications": total_applications,
        "applied_count": applied_count,
        "interview_count": interview_count,
        "review_count": review_count,
        "rejected_count": rejected_count,
        "pending_count": pending_count,
        "today_applied": today_applied,
        "daily_limit": daily_limit,
        "pacing_percentage": pacing_percentage,
        "avg_score": avg_score,
        "applications": applications,
        "top_missing_skills": top_missing_skills,
        "funnel_data": funnel_data,
        "current_status": status_filter,
        "search_query": search_query,
    }
    return render(request, "jobs/dashboard.html", context)


def resume_upload_view(request):
    """Handles PDF resume upload, extracts text and skills, and stores metadata."""
    if request.method == "POST":
        form = ResumeUploadForm(request.POST, request.FILES)
        if form.is_valid():
            resume = form.save(commit=False)
            uploaded_file = request.FILES["file"]

            try:
                extracted_text = extract_text_from_pdf(uploaded_file)
                parsed_meta = parse_resume_metadata(extracted_text)

                resume.parsed_text = extracted_text
                resume.extracted_skills = parsed_meta.get("skills", [])
                resume.metadata = parsed_meta
                resume.save()

                messages.success(
                    request,
                    f"Profile '{resume.name}' added with {len(resume.extracted_skills)} detected skills.",
                )
                return redirect("dashboard")
            except Exception as exc:
                logger.error(f"Error parsing resume PDF: {exc}")
                messages.error(request, f"Failed to parse resume PDF: {str(exc)}")
    else:
        form = ResumeUploadForm()

    recent_resumes = Resume.objects.order_by("-uploaded_at")[:5]
    return render(request, "jobs/upload_resume.html", {"form": form, "recent_resumes": recent_resumes})


def application_detail_view(request, pk: int):
    """Displays deep insights, match evaluation, cover letter, and timeline logs."""
    application = get_object_or_404(Application.objects.select_related("job", "resume"), pk=pk)
    logs = application.logs.order_by("-timestamp")
    status_form = ApplicationStatusUpdateForm(instance=application)

    return render(
        request,
        "jobs/application_detail.html",
        {"application": application, "logs": logs, "status_form": status_form},
    )


@require_POST
def update_application_status_view(request, pk: int):
    """Processes quick status updates for an application."""
    application = get_object_or_404(Application, pk=pk)
    old_status = application.status
    form = ApplicationStatusUpdateForm(request.POST, instance=application)

    if form.is_valid():
        app = form.save()
        if old_status != app.status:
            ApplicationLog.objects.create(
                application=app,
                level=ApplicationLog.LEVEL_INFO,
                message=f"Status manually updated from '{old_status}' to '{app.status}'. Notes: {app.notes}",
            )
            messages.success(request, f"Application status updated to '{app.get_status_display()}'.")
        else:
            messages.info(request, "Application notes updated.")
    else:
        messages.error(request, "Invalid status update data submitted.")

    return redirect("application_detail", pk=pk)


@require_POST
def approve_and_apply_view(request, pk: int):
    """One-click Human-in-the-Loop approval: triggers Playwright for a specific application."""
    application = get_object_or_404(Application, pk=pk)
    pipeline = JobApplicationPipeline(headless=True)

    success = pipeline.apply_to_application(application)
    if success:
        messages.success(request, f"Approved and submitted application for {application.job.title}!")
    else:
        messages.error(request, f"Submission attempt failed for {application.job.title}. Check logs.")

    return redirect("dashboard")


@require_POST
def fetch_jobs_view(request):
    """Triggers the live job ingestion service."""
    fetcher = JobFetcherService()
    new_jobs = fetcher.fetch_and_store_jobs(limit=10)
    messages.success(request, f"Fetched and stored {len(new_jobs)} new job postings.")
    return redirect("dashboard")


@require_POST
def trigger_pipeline_view(request):
    """Triggers the Ollama multi-resume evaluation and auto-apply pipeline."""
    if not Resume.objects.exists():
        messages.warning(request, "Please upload at least one resume profile first.")
        return redirect("resume_upload")

    pipeline = JobApplicationPipeline(headless=True)
    results = pipeline.run_pipeline(job_limit=8, dry_run=False)

    applied = sum(1 for r in results if r["status"] == "AUTO_APPLIED")
    review = sum(1 for r in results if r["status"] == "NEEDS_REVIEW")

    messages.success(
        request,
        f"Pipeline complete! Evaluated {len(results)} jobs: "
        f"{applied} auto-applied, {review} placed in Needs Review.",
    )
    return redirect("dashboard")