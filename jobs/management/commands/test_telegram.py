from django.core.management.base import BaseCommand
from jobs.notifications import TelegramNotificationService


class Command(BaseCommand):
    help = "Tests the Telegram Bot connection by sending a verification ping"

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Testing Telegram Bot Connection..."))

        service = TelegramNotificationService()

        if not service.is_configured:
            self.stdout.write(
                self.style.ERROR(
                    "Error: Telegram Bot credentials are not configured in your .env file!\n"
                    "Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env."
                )
            )
            return

        self.stdout.write(f"Using Bot Token: {service.bot_token[:10]}... (hidden)")
        self.stdout.write(f"Target Chat ID: {service.chat_id}")

        test_message = (
            "🚀 <b>JobBot AI Test Notification</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Your Django backend is connected to the Telegram Bot API.\n"
            "You will receive alerts here whenever an application reaches the <b>Interview</b> stage."
        )

        result = service.send_message(test_message)

        if result.get("success"):
            self.stdout.write(self.style.SUCCESS("✓ Success! Verification message received in Telegram."))
        else:
            self.stdout.write(
                self.style.ERROR(f"✗ Failed to send message. Telegram Error: {result.get('error')}")
            )