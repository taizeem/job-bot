import io
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from pypdf import PdfWriter

from .models import Application, ApplicationLog, JobListing, Resume
from .parsers import extract_text_from_pdf, parse_resume_metadata


def generate_test_pdf_bytes(text_lines: list[str]) -> bytes:
    """Helper to create a valid minimal single-page PDF in memory."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer.getvalue()


class ResumeParserTests(TestCase):
    """Tests for the PDF extraction and regex parsing engine."""

    def test_parse_resume_metadata_success(self):
        sample_resume_text = """
        Johnathan Developer
        Email: john.dev@example.com
        Phone: +1 (555) 456-7890
        Summary: Full-stack engineer with 6+ years of experience in distributed systems.
        Technical Skills: Python, Django, PostgreSQL, Docker, AWS, React, and Git.
        Education: Bachelor of Science in Computer Science from State University.
        """
        parsed = parse_resume_metadata(sample_resume_text)

        self.assertEqual(parsed["email"], "john.dev@example.com")
        self.assertEqual(parsed["phone"], "+1 (555) 456-7890")
        self.assertEqual(parsed["years_experience"], 6)
        self.assertIn("Python", parsed["skills"])
        self.assertIn("Django", parsed["skills"])
        self.assertIn("PostgreSQL", parsed["skills"])
        self.assertIn("Docker", parsed["skills"])
        self.assertIn("Bachelor", parsed["education"])
        self.assertGreater(parsed["word_count"], 20)

    def test_parse_resume_metadata_empty(self):
        parsed = parse_resume_metadata("")
        self.assertEqual(parsed["email"], "")
        self.assertEqual(parsed["phone"], "")
        self.assertEqual(parsed["skills"], [])
        self.assertIsNone(parsed["years_experience"])
        self.assertEqual(parsed["word_count"], 0)

    def test_extract_text_from_valid_pdf_bytes(self):
        pdf_bytes = generate_test_pdf_bytes(["Test Page Content"])
        # Should execute cleanly without raising an exception
        extracted = extract_text_from_pdf(pdf_bytes)
        self.assertIsInstance(extracted, str)

    def test_extract_text_from_corrupted_file_raises_value_error(self):
        corrupted_bytes = b"NOT_A_VALID_PDF_HEADER_DATA"
        with self.assertRaises(ValueError):
            extract_text_from_pdf(corrupted_bytes)


class DatabaseModelsTests(TestCase):
    """Tests to verify database model integrity, relationships, and string representations."""

    def setUp(self):
        self.resume = Resume.objects.create(
            name="Alex Mercer Resume",
            file=SimpleUploadedFile("alex_resume.pdf", b"%PDF-1.4 dummy content", content_type="application/pdf"),
            parsed_text="Alex Mercer - Python Software Architect",
            extracted_skills=["Python", "Django", "Docker"],
            metadata={"email": "alex@mercer.dev", "phone": "555-0199"},
        )

        self.job = JobListing.objects.create(
            title="Senior Backend Engineer",
            company="Acme Corp",
            location="Remote",
            description="Looking for an experienced Django and Python engineer.",
            required_skills=["Python", "Django", "PostgreSQL"],
            url="https://example.com/jobs/acme-senior-backend",
            salary_range="$130k - $160k",
            source="Automated Portal",
        )

    def test_resume_creation_and_string_representation(self):
        self.assertEqual(self.resume.name, "Alex Mercer Resume")
        self.assertIn("Alex Mercer Resume", str(self.resume))
        self.assertEqual(len(self.resume.extracted_skills), 3)

    def test_job_listing_creation_and_string_representation(self):
        self.assertEqual(str(self.job), "Senior Backend Engineer at Acme Corp")
        self.assertEqual(self.job.location, "Remote")

    def test_application_lifecycle(self):
        application = Application.objects.create(
            resume=self.resume,
            job=self.job,
            match_score=94.5,
            status=Application.STATUS_PENDING,
            cover_letter="I am excited to apply for Acme Corp's Backend Engineer role.",
        )

        self.assertEqual(application.status, "PENDING")
        self.assertEqual(application.match_score, 94.5)
        self.assertIn("Senior Backend Engineer", str(application))

        # Transition status to INTERVIEW (will trigger Telegram alerts in Phase 4)
        application.status = Application.STATUS_INTERVIEW
        application.save()
        self.assertEqual(application.status, "INTERVIEW")

    def test_application_log_creation(self):
        application = Application.objects.create(
            resume=self.resume,
            job=self.job,
            match_score=85.0,
        )
        log = ApplicationLog.objects.create(
            application=application,
            level=ApplicationLog.LEVEL_INFO,
            message="Auto-apply bot navigated to application portal successfully.",
        )
        self.assertEqual(log.level, "INFO")
        self.assertIn("Auto-apply bot navigated", str(log))
        self.assertEqual(application.logs.count(), 1)