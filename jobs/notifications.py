import logging
from typing import Any, Dict, Optional
from django.conf import settings
import requests

logger = logging.getLogger(__name__)


class TelegramNotificationService:
    """Dispatches formatted notification messages and alerts via Telegram Bot API."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        timeout: int = 6,
    ):
        # Only fall back to settings when the argument is None, not when explicitly passed as ""
        self.bot_token = (
            getattr(settings, "TELEGRAM_BOT_TOKEN", "")
            if bot_token is None
            else bot_token
        )
        self.chat_id = (
            getattr(settings, "TELEGRAM_CHAT_ID", "")
            if chat_id is None
            else chat_id
        )
        self.timeout = timeout
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    @property
    def is_configured(self) -> bool:
        """Checks if valid credentials have been set in settings or environment."""
        return bool(
            self.bot_token
            and self.chat_id
            and not self.bot_token.startswith("your_")
            and not self.chat_id.startswith("your_")
        )

    def send_message(self, message: str, parse_mode: str = "HTML") -> Dict[str, Any]:
        """
        Sends an HTML-formatted message to the configured Telegram chat.
        """
        if not self.is_configured:
            logger.warning("Telegram notification skipped: Bot token or Chat ID is not configured.")
            return {"success": False, "error": "Credentials missing or unconfigured."}

        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        }

        try:
            response = requests.post(self.api_url, json=payload, timeout=self.timeout)
            response_data = response.json()

            if response.status_code == 200 and response_data.get("ok"):
                logger.info("Telegram message delivered successfully.")
                return {"success": True, "data": response_data}
            else:
                error_desc = response_data.get("description", "Unknown Telegram API error")
                logger.error(f"Telegram API responded with error: {error_desc}")
                return {"success": False, "error": error_desc}

        except requests.Timeout:
            logger.error("Telegram API call timed out.")
            return {"success": False, "error": "Request timed out"}
        except requests.RequestException as exc:
            logger.error(f"Telegram network connection failed: {exc}")
            return {"success": False, "error": str(exc)}

    def notify_interview_scheduled(self, application) -> Dict[str, Any]:
        """
        Formats an interview alert for a specific job application.
        """
        job = application.job
        resume = application.resume
        notes = application.notes or "No additional notes provided."

        message = (
            f"🎉 <b>INTERVIEW SCHEDULED!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Role:</b> {job.title}\n"
            f"<b>Company:</b> {job.company}\n"
            f"<b>Location:</b> {job.location}\n"
            f"<b>AI Match Fit:</b> <code>{application.match_score:.1f}%</code>\n"
            f"<b>Candidate:</b> {resume.name}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Recruiter / Status Notes:</b>\n"
            f"<i>{notes}</i>\n\n"
            f"🔗 <a href='{job.url}'>View Job Posting</a>"
        )

        return self.send_message(message)