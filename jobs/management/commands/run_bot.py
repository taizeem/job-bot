from django.core.management.base import BaseCommand
from jobs.models import JobListing, Resume
from jobs.services import JobApplicationPipeline


class Command(BaseCommand):
    help = "Runs the AI Job Matching and Auto-Apply Pipeline"

    def add_arguments(self, parser):
        parser.add_argument(
            "--threshold",
            type=float,
            default=70.0,
            help="Minimum AI match score required to auto-apply (default: 70.0)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=5,
            help="Maximum number of job listings to process (default: 5)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Evaluate match scores without submitting applications",
        )
        parser.add_argument(
            "--headed",
            action="store_true",
            help="Run browser in visible (headed) mode for debugging",
        )

    def handle(self, *args, **options):
        threshold = options["threshold"]
        limit = options["limit"]
        dry_run = options["dry_run"]
        headless = not options["headed"]

        self.stdout.write(self.style.NOTICE(f"Starting Job Bot (Threshold: {threshold}%, Dry-Run: {dry_run})"))

        # 1. Fetch latest active resume
        resume = Resume.objects.order_by("-uploaded_at").first()
        if not resume:
            self.stdout.write(self.style.WARNING("No resume found in database. Creating a sample resume..."))
            resume = Resume.objects.create(
                name="Alex Mercer (Python Engineer)",
                parsed_text=(
                    "Senior Software Engineer with 5 years experience in Python, Django, "
                    "PostgreSQL, Docker, Git, and REST APIs. Built scalable distributed systems."
                ),
                extracted_skills=["Python", "Django", "PostgreSQL", "Docker", "Git", "REST API"],
                metadata={"email": "alex.mercer@devmail.com", "phone": "+1-555-0199"},
            )
            self.stdout.write(self.style.SUCCESS(f"Created sample resume: {resume.name}"))

        # 2. Seed test jobs if none exist
        if not JobListing.objects.exists():
            self.stdout.write(self.style.NOTICE("No jobs in database. Seeding 3 sample test jobs..."))
            JobListing.objects.create(
                title="Python/Django Backend Engineer",
                company="Nexus Tech",
                location="Remote",
                description="We need a strong Python/Django engineer with Docker and PostgreSQL experience.",
                required_skills=["Python", "Django", "PostgreSQL", "Docker"],
                url="simulation://nexus-tech.io/apply/101",
                source="Simulated Portal",
            )
            JobListing.objects.create(
                title="Full-Stack Python Developer",
                company="CloudWave",
                location="Remote",
                description="Looking for Python, Django, and React developer to build customer-facing dashboards.",
                required_skills=["Python", "Django", "React"],
                url="simulation://cloudwave.net/careers/202",
                source="Simulated Portal",
            )
            JobListing.objects.create(
                title="Java Enterprise Architect",
                company="Legacy Bank Corp",
                location="New York, NY",
                description="Looking for 10+ years Java, Spring Boot, Oracle DB, and mainframe experience.",
                required_skills=["Java", "Spring Boot", "Oracle"],
                url="simulation://[legacybank.com/jobs/999](https://legacybank.com/jobs/999)",
                source="Simulated Portal",
            )
            self.stdout.write(self.style.SUCCESS("Seeded 3 sample job listings."))

        # 3. Execute Pipeline
        pipeline = JobApplicationPipeline(match_threshold=threshold, headless=headless)
        results = pipeline.run_for_resume(resume=resume, job_limit=limit, dry_run=dry_run)

        # 4. Print Summary
        self.stdout.write("\n" + "=" * 55)
        self.stdout.write(self.style.SUCCESS("PIPELINE EXECUTION SUMMARY"))
        self.stdout.write("=" * 55)
        for res in results:
            status = "APPLIED" if res.get("applied") else ("DRY-RUN" if res.get("dry_run") else "SKIPPED")
            self.stdout.write(f"• {res['job']} | Score: {res['score']}% | Result: {status}")
        self.stdout.write("=" * 55 + "\n")