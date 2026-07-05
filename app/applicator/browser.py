"""
Browser automation module using Playwright.

Launches a headed browser instance to navigate to a job application URL,
pre-fills candidate personal information and contact details, uploads the
tailored resume, and pauses to allow the user to review and click submit.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


def launch_application_assistant(
    url: str,
    name: str,
    email: str,
    phone: Optional[str] = None,
    resume_path: Optional[str] = None,
) -> None:
    """Launch headed Playwright browser to pre-fill application details.

    Args:
        url: The application page URL.
        name: Candidate's full name.
        email: Candidate's email address.
        phone: Candidate's phone number.
        resume_path: Path to the tailored resume PDF/Markdown to upload.
    """
    logger.info("Launching Playwright browser assistant for url: %s", url)
    
    with sync_playwright() as p:
        # Launch headed browser so the user can interact
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        # Adjust page viewport size
        page.set_viewport_size({"width": 1280, "height": 800})
        
        # Navigate to target page
        try:
            page.goto(url, wait_until="domcontentloaded")
            logger.info("Successfully navigated to job page.")
        except Exception as e:
            logger.error("Failed to navigate to job page: %s", e)
            browser.close()
            return

        # Pre-filling logic
        try:
            # 1. Fill Name
            # Look for common selectors
            name_selectors = [
                'input[name*="name" i]',
                'input[id*="name" i]',
                'input[placeholder*="name" i]',
                'input[autocomplete*="name" i]'
            ]
            for selector in name_selectors:
                el = page.query_selector(selector)
                if el and el.is_visible() and el.is_enabled():
                    # Check if it's first/last name split
                    if "first" in selector.lower() or "first" in (el.get_attribute("name") or "").lower():
                        # Fill first name (split full name)
                        parts = name.split(" ", 1)
                        el.fill(parts[0])
                        # Try to find last name nearby
                        last_el = page.query_selector('input[name*="last" i], input[name*="surname" i], input[id*="last" i]')
                        if last_el and len(parts) > 1:
                            last_el.fill(parts[1])
                    else:
                        el.fill(name)
                    break

            # 2. Fill Email
            email_selectors = [
                'input[type="email" i]',
                'input[name*="email" i]',
                'input[id*="email" i]',
                'input[placeholder*="email" i]'
            ]
            for selector in email_selectors:
                el = page.query_selector(selector)
                if el and el.is_visible() and el.is_enabled():
                    el.fill(email)
                    break

            # 3. Fill Phone
            if phone:
                phone_selectors = [
                    'input[type="tel" i]',
                    'input[name*="phone" i]',
                    'input[id*="phone" i]',
                    'input[placeholder*="phone" i]'
                ]
                for selector in phone_selectors:
                    el = page.query_selector(selector)
                    if el and el.is_visible() and el.is_enabled():
                        el.fill(phone)
                        break

            # 4. Upload Resume
            if resume_path and os.path.exists(resume_path):
                # Search for file inputs
                file_selectors = [
                    'input[type="file"][accept*="pdf" i]',
                    'input[type="file"][name*="resume" i]',
                    'input[type="file"][id*="resume" i]',
                    'input[type="file"]'
                ]
                for selector in file_selectors:
                    el = page.query_selector(selector)
                    if el:
                        # Set file input
                        el.set_input_files(resume_path)
                        logger.info("Uploaded resume: %s", resume_path)
                        break
                        
        except Exception as fill_err:
            logger.warning("Error encountered during form pre-filling: %s", fill_err)

        # Inform user and keep browser open
        logger.info("Form pre-filling finished. Waiting for user to review and submit...")
        print("\n" + "=" * 70)
        print(" JOB APPLICATION ASSISTANT IS ACTIVE ")
        print(" Please review the pre-filled form in the browser window.")
        print(" Upload any missing files, answer custom questions, and click Submit.")
        print(" Close the browser window or press Enter here when finished to exit.")
        print("=" * 70 + "\n")
        
        # Keep window open until user closes it or hits enter in console
        # Playwright closes the browser when the python process ends or we block
        try:
            # We wait for the browser window to be closed manually by the user
            while browser.is_connected() and len(browser.contexts) > 0:
                # Small wait to prevent 100% CPU usage
                page.wait_for_timeout(1000)
        except Exception:
            pass
        
        logger.info("Browser session closed. Exiting assistant.")
