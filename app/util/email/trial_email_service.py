import logging
from pathlib import Path
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from string import Template
from typing import Optional

from app.config.settings import Settings

settings = Settings()


class TrialEmailService:
    """Service for sending trial-related emails using Mailtrap"""

    def __init__(self):
        self.smtp_server = "live.smtp.mailtrap.io"
        self.smtp_port = 587
        self.sender_email = "ProcLogic Team <team@proclogic.be>"

    def send_trial_welcome_email(self, email: str, company_name: str, trial_end_date: str) -> bool:
        """Send welcome email when trial starts."""
        try:
            email_data = {
                "company_name": company_name,
                "trial_end_date": trial_end_date,
                "frontend_url": settings.frontend_url or "https://proclogic.be"
            }

            email_content = self._get_email_template("trial_welcome_email.html", email_data)
            subject = "🎉 Welkom bij je 7-daagse gratis trial!"

            success = self._send_email(
                recipient_email=email,
                recipient_name=company_name,
                subject=subject,
                content=email_content,
            )

            if success:
                logging.info(f"Trial welcome email sent successfully to {email}")
            
            return success

        except Exception as e:
            logging.error(f"Error sending trial welcome email to {email}: {e}")
            return False

    def send_trial_expiring_email(self, email: str, company_name: str, days_remaining: int) -> bool:
        """Send email notification for trial expiring soon."""
        try:
            email_data = {
                "company_name": company_name,
                "days_remaining": days_remaining,
                "frontend_url": settings.frontend_url or "https://proclogic.be"
            }

            template_name = "trial_expiring_email.html"
            email_content = self._get_email_template(template_name, email_data)
            
            day_text = "dag" if days_remaining == 1 else "dagen"
            subject = f"Je trial verloopt over {days_remaining} {day_text}"

            success = self._send_email(
                recipient_email=email,
                recipient_name=company_name,
                subject=subject,
                content=email_content,
            )

            if success:
                logging.info(f"Trial expiring email sent successfully to {email}")
            
            return success

        except Exception as e:
            logging.error(f"Error sending trial expiring email to {email}: {e}")
            return False

    def send_trial_expired_email(self, email: str, company_name: str) -> bool:
        """Send email notification for expired trial."""
        try:
            email_data = {
                "company_name": company_name,
                "frontend_url": settings.frontend_url or "https://proclogic.be"
            }

            email_content = self._get_email_template("trial_expired_email.html", email_data)
            subject = "🚫 Je trial is verlopen - Upgrade om door te gaan"

            success = self._send_email(
                recipient_email=email,
                recipient_name=company_name,
                subject=subject,
                content=email_content,
            )

            if success:
                logging.info(f"Trial expired email sent successfully to {email}")
            
            return success

        except Exception as e:
            logging.error(f"Error sending trial expired email to {email}: {e}")
            return False

    def _get_email_template(self, template_filename: str, data: dict) -> str:
        """Load and populate email template with data"""
        try:
            template_path = Path(__file__).parent / "email_templates" / template_filename
            
            if not template_path.exists():
                raise FileNotFoundError(f"Email template not found: {template_path}")
            
            with open(template_path, "r", encoding="utf-8") as f:
                template_content = f.read()

            # Use Template class for safe substitution
            template = Template(template_content)
            return template.safe_substitute(data)

        except Exception as e:
            logging.error(f"Error loading email template {template_filename}: {e}")
            raise

    def _send_email(self, recipient_email: str, recipient_name: str, subject: str, content: str) -> bool:
        """Send email using Mailtrap SMTP"""
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.sender_email
            msg["To"] = f"{recipient_name} <{recipient_email}>"

            # Add HTML content
            html_part = MIMEText(content, "html")
            msg.attach(html_part)

            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login("api", settings.mailtrap_token)
                server.send_message(msg)

            logging.info(f"Email sent successfully to {recipient_email}")
            return True

        except Exception as e:
            logging.error(f"Failed to send email to {recipient_email}: {e}")
            return False
