from django.db import models


class Resume(models.Model):
    """Stores uploaded PDF resumes and their parsed extracted text and metadata."""

    name = models.CharField(
        max_length=255,
        default="Candidate Resume",
        help_text="A friendly name or candidate name for this resume.",
    )
    file = models.FileField(
        upload_to="resumes/",
        help_text="Upload your resume in PDF format.",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    parsed_text = models.TextField(
        blank=True,
        default="",
        help_text="Extracted raw text content from the PDF.",
    )
    extracted_skills = models.JSONField(
        default=list,
        blank=True,
        help_text="List of technical skills detected by the parser.",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured metadata including email, phone, and education.",
    )

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return f"{self.name} (Uploaded: {self.uploaded_at.strftime('%Y-%m-%d %H:%M')})"


class JobListing(models.Model):
    """Represents a job vacancy discovered or scraped from job portals."""

    title = models.CharField(max_length=255)
    company = models.CharField(max_length=255)
    location = models.CharField(max_length=255, default="Remote", blank=True)
    description = models.TextField(help_text="Full text of the job description.")
    required_skills = models.JSONField(
        default=list,
        blank=True,
        help_text="Key skills extracted or specified for this role.",
    )
    url = models.URLField(
        max_length=500,
        unique=True,
        help_text="Direct link to the job posting.",
    )
    salary_range = models.CharField(max_length=100, blank=True, default="")
    source = models.CharField(
        max_length=100,
        default="Automated Portal",
        help_text="Portal where the job was discovered (e.g. LinkedIn, Indeed, Portal).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} at {self.company}"


class Application(models.Model):
    """Tracks an application made to a specific job listing using a specific resume."""

    STATUS_PENDING = "PENDING"
    STATUS_APPLIED = "APPLIED"
    STATUS_INTERVIEW = "INTERVIEW"
    STATUS_REJECTED = "REJECTED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending Review / Match"),
        (STATUS_APPLIED, "Applied"),
        (STATUS_INTERVIEW, "Interview Scheduled"),
        (STATUS_REJECTED, "Rejected"),
    ]

    resume = models.ForeignKey(
        Resume,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    job = models.ForeignKey(
        JobListing,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    match_score = models.FloatField(
        default=0.0,
        help_text="AI match score between 0.0 and 100.0.",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    cover_letter = models.TextField(
        blank=True,
        default="",
        help_text="AI-customized cover letter for this submission.",
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the auto-apply bot submitted the form.",
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        unique_together = ("resume", "job")

    def __str__(self) -> str:
        return f"Application for {self.job.title} ({self.status}) - Score: {self.match_score:.1f}%"


class ApplicationLog(models.Model):
    """Detailed audit trail for bot actions, API calls, and status updates."""

    LEVEL_INFO = "INFO"
    LEVEL_WARNING = "WARNING"
    LEVEL_ERROR = "ERROR"

    LEVEL_CHOICES = [
        (LEVEL_INFO, "Info"),
        (LEVEL_WARNING, "Warning"),
        (LEVEL_ERROR, "Error"),
    ]

    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="logs",
        null=True,
        blank=True,
    )
    level = models.CharField(
        max_length=10,
        choices=LEVEL_CHOICES,
        default=LEVEL_INFO,
    )
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] [{self.level}] {self.message[:60]}"