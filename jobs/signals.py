import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Application, ApplicationLog
from .notifications import TelegramNotificationService

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Application)
def track_application_previous_status(sender, instance, **kwargs):
    """
    Caches the previous status in the database before saving so we can detect transitions.
    """
    if instance.pk:
        try:
            previous_instance = Application.objects.get(pk=instance.pk)
            instance._previous_status = previous_instance.status
        except Application.DoesNotExist:
            instance._previous_status = None
    else:
        instance._previous_status = None


@receiver(post_save, sender=Application)
def trigger_interview_notification(sender, instance, created, **kwargs):
    """
    Fires a Telegram notification whenever an application status transitions to INTERVIEW.
    """
    previous_status = getattr(instance, "_previous_status", None)
    current_status = instance.status

    # Trigger only when status changes TO 'INTERVIEW'
    if current_status == Application.STATUS_INTERVIEW and previous_status != Application.STATUS_INTERVIEW:
        logger.info(f"Detected status transition to INTERVIEW for application ID: {instance.id}")

        service = TelegramNotificationService()
        result = service.notify_interview_scheduled(instance)

        if result.get("success"):
            ApplicationLog.objects.create(
                application=instance,
                level=ApplicationLog.LEVEL_INFO,
                message=(
                    f"Telegram alert sent to Chat ID {service.chat_id} "
                    f"for interview with {instance.job.company}."
                ),
            )
        else:
            error_reason = result.get("error", "Unknown error")
            ApplicationLog.objects.create(
                application=instance,
                level=ApplicationLog.LEVEL_WARNING,
                message=f"Telegram alert could not be delivered: {error_reason}",
            )