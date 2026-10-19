import logging
from django.contrib import messages
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import ApplicationStatusUpdateForm, ResumeUploadForm
from .models import Application, ApplicationLog, JobListing, Resume
from .parsers import extract_text_from_pdf, parse_resume_metadata
from .services import JobApplicationPipeline

logger = logging.getLogger(__name__)


def dashboard_view(request):
    """Main tracking dashboard view displaying metrics, applications, and logs."""
    # Aggregated KPI metrics
    total_resumes = Resume.objects.count()
    total_jobs = JobListing.objects.count()
    total_applications = Application.objects.count()
    applied_count = Application.objects.filter(status=Application.STATUS_APPLIED).count()
    interview_count = Application.objects.filter(status=Application.STATUS_INTERVIEW).count()
    rejected_count = Application.objects.filter(status=Application.STATUS_REJECTED).count()
    avg_score = Application.objects.aggregate(avg=Avg("match_score"))["avg"] or 0.0

    # Search & Filtering
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

    # Recent activity logs
    recent_logs = ApplicationLog.objects.select_related("application", "application__job").order_by("-timestamp")[:10]

    # Active resume (most recently uploaded)
    active_resume = Resume.objects.order_by("-uploaded_at").first()

    context = {
        "total_resumes": total_resumes,
        "total_jobs": total_jobs,
        "total_applications": total_applications,
        "applied_count": applied_count,
        "interview_count": interview_count,
        "rejected_count": rejected_count,
        "avg_score": round(avg_score, 1),
        "applications": applications,
        "recent_logs": recent_logs,
        "active_resume": active_resume,
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
                # Read PDF and extract text
                extracted_text = extract_text_from_pdf(uploaded_file)
                parsed_meta = parse_resume_metadata(extracted_text)

                resume.parsed_text = extracted_text
                resume.extracted_skills = parsed_meta.get("skills", [])
                resume.metadata = parsed_meta
                resume.save()

                messages.success(
                    request,
                    f"Resume '{resume.name}' parsed successfully! "
                    f"Detected {len(resume.extracted_skills)} skills and {parsed_meta.get('word_count', 0)} words.",
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
        {
            "application": application,
            "logs": logs,
            "status_form": status_form,
        },
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
def trigger_pipeline_view(request):
    """Triggers the Ollama AI matching and auto-apply pipeline for the latest resume."""
    active_resume = Resume.objects.order_by("-uploaded_at").first()

    if not active_resume:
        messages.warning(request, "Please upload a resume first before triggering the bot.")
        return redirect("resume_upload")

    # Seed test jobs if database has none
    if not JobListing.objects.exists():
        JobListing.objects.create(
            title="Senior Python & Django Architect",
            company="Vertex Cloud Systems",
            location="Remote",
            description="Looking for an engineer with strong Python, Django, PostgreSQL, and Docker experience.",
            required_skills=["Python", "Django", "PostgreSQL", "Docker"],
            url="simulation://vertex.io/apply/1",
        )
        JobListing.objects.create(
            title="Full-Stack Web Developer",
            company="Horizon Digital",
            location="Remote",
            description="Build modern web dashboards with Django, React, and REST APIs.",
            required_skills=["Python", "Django", "React"],
            url="simulation://horizon.com/apply/2",
        )

    pipeline = JobApplicationPipeline(match_threshold=70.0, headless=True)
    results = pipeline.run_for_resume(resume=active_resume, job_limit=5, dry_run=False)

    applied_count = sum(1 for r in results if r.get("applied"))
    messages.success(
        request,
        f"Bot run complete! Evaluated {len(results)} jobs using Ollama. Successfully auto-applied to {applied_count} positions.",
    )
    return redirect("dashboard")