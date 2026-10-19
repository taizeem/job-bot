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
from .notifications import TelegramNotificationService
from .parsers import extract_text_from_pdf, parse_resume_metadata
from .services import JobApplicationPipeline


def generate_test_pdf_bytes(text_lines: list[str]) -> bytes:
    """Creates a valid single-page PDF in memory for tests."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer.getvalue()


# ==========================================
# Phase 1 Tests: Parser & Database Models
# ==========================================
class ResumeParserTests(TestCase):
    def test_parse_resume_metadata_success(self):
        sample = """
        Jane Doe
        Email: jane@test.com | Phone: (555) 000-1111
        Engineer with 4 years of experience in Python, Django, Docker, AWS.
        Education: Bachelor of Science in Computer Science.
        """
        parsed = parse_resume_metadata(sample)
        self.assertEqual(parsed["email"], "jane@test.com")
        self.assertEqual(parsed["phone"], "(555) 000-1111")
        self.assertEqual(parsed["years_experience"], 4)
        self.assertIn("Python", parsed["skills"])
        self.assertIn("Django", parsed["skills"])
        self.assertIn("Docker", parsed["skills"])
        self.assertIn("Bachelor", parsed["education"])

    def test_parse_resume_metadata_empty(self):
        parsed = parse_resume_metadata("")
        self.assertEqual(parsed["email"], "")
        self.assertEqual(parsed["skills"], [])
        self.assertIsNone(parsed["years_experience"])

    def test_extract_text_from_valid_pdf_bytes(self):
        pdf_bytes = generate_test_pdf_bytes(["Sample Test Page"])
        extracted = extract_text_from_pdf(pdf_bytes)
        self.assertIsInstance(extracted, str)

    def test_extract_text_from_corrupted_file(self):
        with self.assertRaises(ValueError):
            extract_text_from_pdf(b"INVALID_HEADER_DATA")


class DatabaseModelsTests(TestCase):
    def setUp(self):
        self.resume = Resume.objects.create(
            name="Alex Mercer",
            parsed_text="Python Engineer",
            extracted_skills=["Python", "Django"],
            metadata={"email": "alex@mercer.dev"},
        )
        self.job = JobListing.objects.create(
            title="Senior Developer",
            company="Acme Corp",
            location="Remote",
            description="Looking for an experienced engineer.",
            required_skills=["Python"],
            url="https://example.com/jobs/acme",
        )

    def test_model_string_representations(self):
        self.assertIn("Alex Mercer", str(self.resume))
        self.assertEqual(str(self.job), "Senior Developer at Acme Corp")

    def test_application_and_log_creation(self):
        app = Application.objects.create(
            resume=self.resume,
            job=self.job,
            match_score=88.0,
            status=Application.STATUS_APPLIED,
        )
        log = ApplicationLog.objects.create(
            application=app,
            level=ApplicationLog.LEVEL_INFO,
            message="Application submitted successfully.",
        )
        self.assertEqual(app.status, "APPLIED")
        self.assertEqual(app.logs.count(), 1)
        self.assertIn("Application submitted", str(log))


# ==========================================
# Phase 2 Tests: Matching & Browser Automation
# ==========================================
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

    def test_heuristic_low_match(self):
        resume_text = "Proficient in Python and Django."
        resume_skills = ["Python", "Django"]
        result = self.engine.evaluate_fit(
            resume_text=resume_text,
            resume_skills=resume_skills,
            job_title="Embedded Firmware Engineer",
            job_description="Requires C, C++, Assembly, microcontrollers, and hardware schematics.",
            required_skills=["C++", "Assembly", "Microcontrollers"],
        )
        self.assertLessEqual(result["match_score"], 40.0)
        self.assertIn("missing_skills", result)

    @patch("jobs.matching.ollama.Client")
    def test_ollama_matching_mock(self, mock_client_class):
        mock_client = MagicMock()
        mock_response = {
            "message": {
                "content": json.dumps({
                    "match_score": 92.0,
                    "summary": "Excellent fit for backend role.",
                    "matching_skills": ["Python", "Django"],
                    "missing_skills": ["AWS"],
                    "cover_letter": "I am excited to apply for this position.",
                })
            }
        }
        mock_client.chat.return_value = mock_response
        mock_client_class.return_value = mock_client

        engine = AIMatchingEngine()
        result = engine.evaluate_fit(
            resume_text="Python Django developer with 5 years experience.",
            resume_skills=["Python", "Django"],
            job_title="Backend Developer",
            job_description="Looking for Python and Django.",
            required_skills=["Python", "Django"],
        )
        self.assertEqual(result["match_score"], 92.0)
        self.assertIn("Python", result["matching_skills"])
        self.assertEqual(result["summary"], "Excellent fit for backend role.")


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


# ==========================================
# Phase 3 Tests: Web Views & Forms
# ==========================================
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
            {"status": Application.STATUS_APPLIED, "notes": "Application confirmed."},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.STATUS_APPLIED)

    def test_trigger_pipeline_view(self):
        response = self.client.post(reverse("trigger_bot"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "jobs/dashboard.html")


# ==========================================
# Phase 4 Tests: Telegram Bot & Signals
# ==========================================
class TelegramNotificationTests(TestCase):
    def setUp(self):
        self.service = TelegramNotificationService(bot_token="test_token", chat_id="123456")

    @patch("jobs.notifications.requests.post")
    def test_send_message_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 99}}
        mock_post.return_value = mock_response

        res = self.service.send_message("Test message")
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["result"]["message_id"], 99)

    def test_service_unconfigured_skips_call(self):
        unconfigured_service = TelegramNotificationService(bot_token="", chat_id="")
        self.assertFalse(unconfigured_service.is_configured)
        res = unconfigured_service.send_message("Hello")
        self.assertFalse(res["success"])
        self.assertIn("missing or unconfigured", res["error"])


class TelegramSignalIntegrationTests(TestCase):
    def setUp(self):
        self.resume = Resume.objects.create(name="Signal Test Candidate")
        self.job = JobListing.objects.create(
            title="Backend Lead",
            company="Starlight Labs",
            description="Django, Python",
            url="simulation://starlight.io/1",
        )
        self.application = Application.objects.create(
            resume=self.resume,
            job=self.job,
            match_score=91.0,
            status=Application.STATUS_APPLIED,
        )

    @patch("jobs.notifications.TelegramNotificationService.send_message")
    def test_transition_to_interview_triggers_signal_and_logs(self, mock_send):
        mock_send.return_value = {"success": True, "data": {}}

        # Transition status to INTERVIEW
        self.application.status = Application.STATUS_INTERVIEW
        self.application.notes = "Round 1 interview scheduled."
        self.application.save()

        # Check that Telegram send_message was triggered
        self.assertTrue(mock_send.called)

        # Check that an ApplicationLog was written
        log_entry = ApplicationLog.objects.filter(
            application=self.application,
            message__icontains="Telegram alert sent",
        ).first()
        self.assertIsNotNone(log_entry)

    @patch("jobs.notifications.TelegramNotificationService.send_message")
    def test_saving_without_status_change_does_not_retrigger(self, mock_send):
        mock_send.return_value = {"success": True}

        self.application.notes = "Updated notes only."
        self.application.save()

        self.assertFalse(mock_send.called)


# ==========================================
# Phase 5 Tests: End-to-End System Simulation
# ==========================================
class EndToEndPipelineTests(TestCase):
    """
    Tests the entire user lifecycle end-to-end:
    PDF Upload -> Skills Extracted -> Matching Engine -> Playwright Auto-Apply ->
    Interview Scheduled -> Signal -> Telegram Alert Dispatch.
    """

    @patch("jobs.notifications.TelegramNotificationService.send_message")
    def test_complete_job_application_lifecycle(self, mock_telegram_send):
        mock_telegram_send.return_value = {"success": True, "data": {}}

        # 1. Simulate Candidate uploading a PDF Resume
        pdf_bytes = generate_test_pdf_bytes(["Test Candidate Resume Content"])
        pdf_file = SimpleUploadedFile("candidate_cv.pdf", pdf_bytes, content_type="application/pdf")

        resume = Resume.objects.create(
            name="Dev Candidate E2E",
            file=pdf_file,
            parsed_text="Senior Python Engineer with 6 years experience in Django, PostgreSQL, and Docker.",
            extracted_skills=["Python", "Django", "PostgreSQL", "Docker"],
            metadata={"email": "e2e@candidate.dev", "phone": "+1-555-9000"},
        )
        self.assertEqual(resume.extracted_skills, ["Python", "Django", "PostgreSQL", "Docker"])

        # 2. Seed a High-Match Job Posting
        target_job = JobListing.objects.create(
            title="Senior Django Developer",
            company="NextGen AI Labs",
            location="Remote",
            description="We are seeking an experienced Python and Django developer with PostgreSQL skills.",
            required_skills=["Python", "Django", "PostgreSQL"],
            url="simulation://nextgen.ai/apply/909",
            source="Automated Portal",
        )

        # 3. Execute Pipeline Orchestrator (Ollama matching + Browser Bot)
        pipeline = JobApplicationPipeline(match_threshold=70.0, headless=True)
        results = pipeline.run_for_resume(resume=resume, job_limit=1, dry_run=False)

        # 4. Verify Application was auto-submitted
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["applied"])
        self.assertGreaterEqual(results[0]["score"], 70.0)

        application = Application.objects.get(job=target_job, resume=resume)
        self.assertEqual(application.status, Application.STATUS_APPLIED)
        self.assertIsNotNone(application.applied_at)
        self.assertTrue(application.logs.filter(message__icontains="Auto-applied successfully").exists())

        # 5. Simulate Recruiter reaching out -> Status updated to INTERVIEW
        application.status = Application.STATUS_INTERVIEW
        application.notes = "Technical interview scheduled with Principal Engineer."
        application.save()

        # 6. Verify Telegram Alert hook fired automatically
        self.assertTrue(mock_telegram_send.called)
        self.assertTrue(application.logs.filter(message__icontains="Telegram alert sent").exists())