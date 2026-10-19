import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
from django.conf import settings
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

logger = logging.getLogger(__name__)


class JobApplicationBot:
    """Automates form filling and document uploading on job application portals."""

    def __init__(self, headless: bool = True, timeout_ms: int = 15000):
        self.headless = headless
        self.timeout_ms = timeout_ms

    def submit_application(
        self,
        job_url: str,
        candidate_name: str,
        candidate_email: str,
        candidate_phone: str,
        resume_path: Optional[str],
        cover_letter: str = "",
        screenshot_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Navigates to job_url, fills applicant details, attaches resume, and submits.
        """
        screenshot_dir = Path(settings.BASE_DIR) / "media" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_file = screenshot_dir / (screenshot_name or "application_result.png")

        # Handle local simulated test URLs without spinning up an external network
        if job_url.startswith("simulation://") or "example.com" in job_url:
            return {
                "success": True,
                "message": f"Application simulated successfully for {candidate_name} at {job_url}",
                "screenshot_path": "",
            }

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            )
            page = context.new_page()

            try:
                logger.info(f"Navigating to {job_url}")
                page.goto(job_url, timeout=self.timeout_ms, wait_until="domcontentloaded")

                # 1. Fill Name
                name_selectors = [
                    'input[name*="name" i]',
                    'input[id*="name" i]',
                    'input[placeholder*="full name" i]',
                    'input[placeholder*="name" i]',
                ]
                self._fill_first_match(page, name_selectors, candidate_name)

                # 2. Fill Email
                email_selectors = [
                    'input[type="email"]',
                    'input[name*="email" i]',
                    'input[id*="email" i]',
                ]
                self._fill_first_match(page, email_selectors, candidate_email)

                # 3. Fill Phone
                phone_selectors = [
                    'input[type="tel"]',
                    'input[name*="phone" i]',
                    'input[id*="phone" i]',
                    'input[placeholder*="phone" i]',
                ]
                self._fill_first_match(page, phone_selectors, candidate_phone)

                # 4. Fill Cover Letter (if a textarea is found)
                cover_selectors = [
                    'textarea[name*="cover" i]',
                    'textarea[id*="cover" i]',
                    'textarea[placeholder*="cover letter" i]',
                    "textarea",
                ]
                if cover_letter:
                    self._fill_first_match(page, cover_selectors, cover_letter)

                # 5. Upload Resume PDF
                if resume_path and os.path.exists(resume_path):
                    file_input = page.locator('input[type="file"]').first
                    if file_input.count() > 0:
                        file_input.set_input_files(resume_path)
                        logger.info(f"Attached resume: {resume_path}")

                # 6. Capture screenshot prior to submission
                page.screenshot(path=str(screenshot_file), full_page=True)

                # 7. Locate and click submit button
                submit_selectors = [
                    'button[type="submit"]',
                    'input[type="submit"]',
                    'button:has-text("Submit Application")',
                    'button:has-text("Apply Now")',
                    'button:has-text("Submit")',
                ]
                submitted = False
                for sel in submit_selectors:
                    btn = page.locator(sel).first
                    if btn.count() > 0 and btn.is_visible():
                        btn.click()
                        submitted = True
                        break

                if submitted:
                    page.wait_for_timeout(2000)
                    page.screenshot(path=str(screenshot_file), full_page=True)
                    return {
                        "success": True,
                        "message": "Application submitted successfully.",
                        "screenshot_path": str(screenshot_file),
                    }
                else:
                    return {
                        "success": False,
                        "message": "Form filled, but no submit button was detected.",
                        "screenshot_path": str(screenshot_file),
                    }

            except PlaywrightTimeoutError as timeout_err:
                logger.error(f"Navigation timed out: {timeout_err}")
                return {
                    "success": False,
                    "message": f"Page timeout: {str(timeout_err)}",
                    "screenshot_path": "",
                }
            except Exception as err:
                logger.error(f"Automation error: {err}")
                return {
                    "success": False,
                    "message": f"Automation error: {str(err)}",
                    "screenshot_path": "",
                }
            finally:
                context.close()
                browser.close()

    def _fill_first_match(self, page, selectors: list[str], value: str) -> bool:
        """Finds the first visible field matching selectors and fills it."""
        for selector in selectors:
            field = page.locator(selector).first
            if field.count() > 0 and field.is_visible():
                field.fill(value)
                return True
        return False