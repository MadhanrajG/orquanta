"""OrQuanta Agentic v1.0 — Notifications package."""
from .email_templates import EmailTemplates, Email
from .notification_service import (
    NotificationService, NotificationEvent, UserNotificationPrefs,
    NotificationRecord, Channel, Priority, get_notification_service,
)

__all__ = [
    "EmailTemplates", "Email",
    "NotificationService", "NotificationEvent", "UserNotificationPrefs",
    "NotificationRecord", "Channel", "Priority", "get_notification_service",
]
