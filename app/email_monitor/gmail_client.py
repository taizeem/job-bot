"""
Gmail client module for polling and reading job-related emails.

Utilizes Google OAuth2 flow and Gmail API to fetch emails, classify them,
update application statuses in the database, and trigger notifications.
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import Application, Job, Log
from app.email_monitor.classifier import classify_email
from app.notifications.telegram_bot import notify_interview_invitation

logger = logging.getLogger(__name__)

# Scopes required to read and manage emails
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",  # Needed to mark emails as read/processed
]


def get_gmail_service() -> Any:
    """Authenticate and return the Gmail API service client.

    Returns:
        Gmail API service instance, or None if credentials are not configured.
    """
    creds_path = Path(settings.gmail_credentials_path)
    token_path = Path("data/token.json")
    
    creds = None
    
    # Check if we have a cached oauth token
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception as e:
            logger.warning("Failed to load cached Gmail token: %s", e)
            
    # If no cached token or token is invalid, run flow if credentials.json is present
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_path, "w") as token:
                    token.write(creds.to_json())
            except Exception as e:
                logger.error("Failed to refresh Gmail OAuth token: %s", e)
                creds = None
                
        if not creds:
            if not creds_path.exists():
                logger.warning(
                    "Gmail client credentials file not found at %s. "
                    "Skipping Gmail monitor setup. See README for instructions.",
                    creds_path
                )
                return None
                
            try:
                flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
                creds = flow.run_local_server(port=0)
                # Cache token
                token_path.parent.mkdir(parents=True, exist_ok=True)
                with open(token_path, "w") as token:
                    token.write(creds.to_json())
            except Exception as e:
                logger.error("Failed to run Google OAuth flow: %s", e)
                return None

    try:
        service = build("gmail", "v1", credentials=creds)
        return service
    except Exception as e:
        logger.error("Failed to build Gmail service: %s", e)
        return None


def get_or_create_label(service: Any, label_name: str) -> str:
    """Find or create a custom label in Gmail to tag processed emails."""
    try:
        results = service.users().labels().list(userId="me").execute()
        labels = results.get("labels", [])
        for label in labels:
            if label["name"].lower() == label_name.lower():
                return label["id"]
                
        # Create new label
        label_body = {
            "name": label_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show"
        }
        new_label = service.users().labels().create(userId="me", body=label_body).execute()
        logger.info("Created Gmail label: %s", label_name)
        return new_label["id"]
    except Exception as e:
        logger.error("Failed to fetch or create label %s: %s", label_name, e)
        raise


def check_and_classify_emails(db: Session) -> dict[str, int]:
    """Poll Gmail for new job-related emails and classify them."""
    service = get_gmail_service()
    if not service:
        return {"checked": 0, "classified": 0}

    # Ensure label "JobBot_Processed" exists
    label_name = "JobBot_Processed"
    try:
        label_id = get_or_create_label(service, label_name)
    except Exception:
        return {"checked": 0, "classified": 0}

    # Query Gmail for inbox emails NOT tagged with processed label
    # E.g. search for keywords in subject/sender
    query = f"subject:(interview OR application OR assessment OR offer OR hiring OR recruitment) -label:{label_name}"
    
    checked = 0
    classified_count = 0
    
    try:
        results = service.users().messages().list(userId="me", q=query).execute()
        messages = results.get("messages", [])
        
        if not messages:
            logger.info("No new job-related emails to process.")
            return {"checked": 0, "classified": 0}
            
        logger.info("Found %d raw email candidates in inbox.", len(messages))
        
        for msg in messages:
            checked += 1
            msg_id = msg["id"]
            
            # Fetch message content
            try:
                full_msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
                payload = full_msg.get("payload", {})
                snippet = full_msg.get("snippet", "")
                
                # Extract headers
                headers = payload.get("headers", [])
                subject = ""
                sender = ""
                for h in headers:
                    if h["name"].lower() == "subject":
                        subject = h["value"]
                    if h["name"].lower() == "from":
                        sender = h["value"]
                
                # Classify the email
                classification = classify_email(subject, snippet)
                category = classification.category
                
                logger.info(
                    "Email '%s' classified as %s (Reason: %s)",
                    subject, category, classification.reasoning
                )
                
                # Skip irrelevant emails
                if category == "irrelevant":
                    # Mark as processed so we don't look at it again
                    service.users().messages().modify(
                        userId="me",
                        id=msg_id,
                        body={"addLabelIds": [label_id]}
                    ).execute()
                    continue
                
                # Try to map to an active application
                company = classification.company_name
                if company:
                    # Find a job matching the company name
                    db_job = db.query(Job).filter(
                        Job.company.ilike(f"%{company}%")
                    ).first()
                    
                    if db_job:
                        app = db.query(Application).filter(Application.job_id == db_job.id).first()
                        if not app:
                            # Auto-create application entry if not tracked
                            app = Application(job_id=db_job.id, status="pending")
                            db.add(app)
                        
                        # Map category to application status
                        status_map = {
                            "rejection": "rejected",
                            "interview": "interview",
                            "offer": "offer"
                        }
                        if category in status_map:
                            app.status = status_map[category]
                            db.add(Log(
                                event="email",
                                source="GmailMonitor",
                                message=f"Updated status for {db_job.title} at {db_job.company} to '{app.status}' based on email."
                            ))
                            db.commit()
                            
                # If it's an interview invitation, trigger Telegram alert
                if category == "interview":
                    notify_interview_invitation(
                        company=company or sender or "Unknown",
                        subject=subject,
                        snippet=snippet,
                    )
                
                # Mark as processed
                service.users().messages().modify(
                    userId="me",
                    id=msg_id,
                    body={"addLabelIds": [label_id]}
                ).execute()
                
                classified_count += 1
                
            except Exception as e:
                logger.error("Failed to process message %s: %s", msg_id, e)
                
    except Exception as e:
        logger.error("Failed to query Gmail messages: %s", e)
        
    return {"checked": checked, "classified": classified_count}
