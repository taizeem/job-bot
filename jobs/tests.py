import io
import json
from unittest.mock import MagicMock, patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from pypdf import PdfWriter

from .automation import JobApplicationBot
from .forms import ApplicationStatusUpdateForm, ResumeUploadForm
from .matching import AIMatchingEngine
from .models import Application, ApplicationLog, JobListing, Resume
from .parsers import extract_text_from_pdf, parse_resume_metadata
from .services import JobApplicationPipeline


def generate_test_pdf_bytes(text_lines: list[str]) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer.getvalue()


class ResumeParserTests(TestCase):
    def test_parse_resume_metadata_success(self):
        sample = """
        Jane Doe
        Email: jane@test.com | Phone: (555) 000-1111
        Engineer with 4 years of experience in Python, Django, Docker, AWS.
        Education: Bachelor of Science.
        """
        parsed = parse_resume_metadata(sample)
        self.assertEqual(parsed["email"], "jane@test.com")
        self.assertEqual(parsed["phone"], "(555) 000-1111")
        self.assertEqual(parsed["years_experience"], 4)
        self.assertIn("Python", parsed["skills"])
        self.assertIn("Django", parsed["skills"])

    def test_extract_text_from_corrupted_file(self):
        with self.assertRaises(ValueError):
            extract_text_from_pdf(b"INVALID_HEADER")


class AIMatchingEngineTests(TestCase):
    def setUp(self):
        self.engine = AIMatchingEngine()

    def test_heuristic_high_match(self):
        resume_text = "Experienced with Python, Django, PostgreSQL, Docker, Git, and Linux."
        resume_skills = ["Python", "Django", "PostgreSQL", "Docker"]
        result = self.engine.evaluate_fit(
            resume_text=resume_text,
            resume_skills=resume_skills,
            job_title="Django Backend Developer",
            job_description="Seeking a Python and Django developer with PostgreSQL and Docker.",
            required_skills=["Python", "Django", "PostgreSQL", "Docker"],
        )
        self.assertGreaterEqual(result["match_score"], 80.0)
        self.assertIn("Python", result["matching_skills"])
        self.assertIn("cover_letter", result)


class JobApplicationBotTests(TestCase):
    def test_simulation_url_success(self):
        bot = JobApplicationBot(headless=True)
        res = bot.submit_application(
            job_url="simulation://test-portal/apply",
            candidate_name="Alex Mercer",
            candidate_email="alex@test.com",
            candidate_phone="555-0100",
            resume_path=None,
        )
        self.assertTrue(res["success"])
        self.assertIn("simulated successfully", res["message"])


class WebDashboardAndViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.resume = Resume.objects.create(
            name="Sarah Connor",
            parsed_text="Full Stack Python and Django Specialist",
            extracted_skills=["Python", "Django"],
            metadata={"email": "sarah@connor.dev", "phone": "555-4321"},
        )
        self.job = JobListing.objects.create(
            title="Python Developer",
            company="Cyberdyne Systems",
            description="Django, Python, and SQLite.",
            required_skills=["Python", "Django"],
            url="simulation://cyberdyne.com/job/1",
        )
        self.application = Application.objects.create(
            resume=self.resume,
            job=self.job,
            match_score=85.0,
            status=Application.STATUS_APPLIED,
        )

    def test_dashboard_view_loads_successfully(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "jobs/dashboard.html")
        self.assertContains(response, "Python Developer")
        self.assertContains(response, "Cyberdyne Systems")

    def test_resume_upload_view_get(self):
        response = self.client.get(reverse("resume_upload"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "jobs/upload_resume.html")

    def test_resume_upload_valid_pdf_post(self):
        pdf_bytes = generate_test_pdf_bytes(["Test Content"])
        pdf_file = SimpleUploadedFile("test_resume.pdf", pdf_bytes, content_type="application/pdf")

        response = self.client.post(
            reverse("resume_upload"),
            {"name": "New Candidate", "file": pdf_file},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Resume.objects.filter(name="New Candidate").exists())

    def test_application_detail_view(self):
        response = self.client.get(reverse("application_detail", args=[self.application.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "jobs/application_detail.html")
        self.assertContains(response, "Cyberdyne Systems")

    def test_update_status_view(self):
        response = self.client.post(
            reverse("update_status", args=[self.application.id]),
            {"status": Application.STATUS_INTERVIEW, "notes": "Interview scheduled for Tuesday"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.STATUS_INTERVIEW)
        self.assertIn("Interview scheduled", self.application.notes)

    def test_trigger_pipeline_view(self):
        response = self.client.post(reverse("trigger_bot"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "jobs/dashboard.html")