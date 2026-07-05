"""
Telegram Bot notifications module.

Sends formatted job alerts, status changes, and interview invitations
to the user's Telegram chat.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def send_telegram_message(text: str, parse_mode: str = "HTML") -> bool:
    """Send a formatted text message to the Telegram chat.

    Args:
        text: The message content (HTML formatted).
        parse_mode: Parsing mode ('HTML' or 'Markdown').

    Returns:
        True if the message was sent successfully, False otherwise.
    """
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    
    if not token or not chat_id:
        logger.warning("Telegram Bot Token or Chat ID not configured. Skipping notification.")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False
    }
    
    try:
        # Use sync request for simple invocation from anywhere
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            logger.debug("Telegram message sent successfully.")
            return True
    except Exception as e:
        logger.error("Failed to send Telegram message: %s", e)
        return False


def notify_high_match_job(
    job_title: str,
    company: str,
    location: str,
    salary: str | None,
    match_score: float,
    job_url: str,
) -> bool:
    """Send alert for a newly discovered job with a high match score."""
    score_pct = int(match_score * 100)
    
    # Escape HTML characters in strings
    title_esc = job_title.replace("<", "&lt;").replace(">", "&gt;")
    company_esc = company.replace("<", "&lt;").replace(">", "&gt;")
    loc_esc = (location or "Remote").replace("<", "&lt;").replace(">", "&gt;")
    sal_str = f"💰 <b>Salary:</b> {salary}\n" if salary else ""
    
    text = (
        f"🔥 <b>New High Match Job Discovered! ({score_pct}%)</b>\n\n"
        f"💼 <b>Role:</b> {title_esc}\n"
        f"🏢 <b>Company:</b> {company_esc}\n"
        f"📍 <b>Location:</b> {loc_esc}\n"
        f"{sal_str}"
        f"🔗 <a href='{job_url}'>View Posting Link</a>\n\n"
        f"<i>Log in to your dashboard to tailor your resume and cover letter!</i>"
    )
    return send_telegram_message(text)


def notify_interview_invitation(
    company: str,
    subject: str,
    snippet: str,
    date_str: str = "TBD",
    time_str: str = "TBD",
    link: str | None = None,
) -> bool:
    """Send alert for a detected interview email."""
    company_esc = company.replace("<", "&lt;").replace(">", "&gt;")
    subject_esc = subject.replace("<", "&lt;").replace(">", "&gt;")
    snippet_esc = snippet.replace("<", "&lt;").replace(">", "&gt;")
    link_str = f"\n🔗 <b>Join Link:</b> <a href='{link}'>{link}</a>" if link else ""
    
    text = (
        f"🔔 <b>Interview Invitation Received!</b>\n\n"
        f"🏢 <b>Company:</b> {company_esc}\n"
        f"📧 <b>Subject:</b> {subject_esc}\n"
        f"📅 <b>Date:</b> {date_str}\n"
        f"⏰ <b>Time:</b> {time_str}\n"
        f"{link_str}\n\n"
        f"📝 <b>Snippet:</b>\n<i>\"{snippet_esc[:200]}...\"</i>"
    )
    return send_telegram_message(text)


def notify_daily_digest(
    total_scraped: int,
    new_jobs: int,
    high_matches: int,
    applied_today: int,
) -> bool:
    """Send daily activity summary to the user."""
    text = (
        f"📊 <b>Daily Job Bot Summary</b>\n\n"
        f"🔍 <b>Jobs Scraped:</b> {total_scraped}\n"
        f"✨ <b>New Additions:</b> {new_jobs}\n"
        f"🔥 <b>High Match Opportunities:</b> {high_matches}\n"
        f"📝 <b>Applications Sent Today:</b> {applied_today}\n\n"
        f"Good luck with your search!"
    )
    return send_telegram_message(text)
