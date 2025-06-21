import logging
from pathlib import Path
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from string import Template
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.models.email_models import ContractEmailTracking
from app.models.publication_contract_models import Contract
from app.models.publication_models import Publication
from app.util.publication_utils.publication_converter import PublicationConverter

settings = Settings()


class ContractEmailService:
    """Service for sending automated emails to contract winners"""

    def __init__(self):
        self.smtp_server = "live.smtp.mailtrap.io"
        self.smtp_port = 587
        self.sender_email = "ProcLogic Team <team@proclogic.be>"

    async def send_contract_winner_email(
        self, publication: Publication, session: Session
    ) -> bool:
        """
        Send personalized email to contract winner and track it in database

        Args:
            contract: The contract object with winner information
            session: Database session
            custom_message: Optional custom message to include

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        contract = publication.contract
        if not contract.winning_publisher:
            logging.warning(f"Contract {contract.contract_id} has no winning publisher")
            return False

        if not contract.winning_publisher.email:
            logging.warning(
                f"Contract {contract.contract_id} winner has no email address"
            )
            return False

        if any(domain in contract.winning_publisher.email.lower() for domain in ["@3p", "@raadvanstate"]): # yeah lets not send to them, normally not needed
            logging.warning(
                f"Contract {contract.contract_id} winner email is not allowed: {contract.winning_publisher.email}"
            )
            return False
        
        try:
            email_content = self._get_email_template(publication=publication)

            # Create email subject
            subject = f"Gefeliciteerd met je gunning! Ontdek hoe ProcLogic je verder kan helpen."

            # Send the email
            success = await self._send_email(
                recipient_email=contract.winning_publisher.email,
                recipient_name=contract.winning_publisher.name,
                subject=subject,
                content=email_content,
            )

            # Track the email in database
            await self._track_email(
                contract=contract,
                recipient_email=contract.winning_publisher.email,
                recipient_name=contract.winning_publisher.name,
                subject=subject,
                content=email_content,
                is_delivered=success,
                session=session,
            )

            return success

        except Exception as e:
            logging.error(
                f"Error sending contract winner email for {contract.contract_id}: {e}"
            )
            # Track failed email
            await self._track_email(
                contract=contract,
                recipient_email=contract.winning_publisher.email,
                recipient_name=contract.winning_publisher.name,
                subject=f"Contract Award Notification - {contract.notice_id}",
                content="Email generation failed",
                is_delivered=False,
                delivery_error=str(e),
                session=session,
            )
            return False

    def _get_email_template(self, publication: Publication) -> str:
        """Generate email template with proper formatting"""
        # Prepare contract data for personalization
        title = PublicationConverter.get_descr_as_str(publication.dossier.titles)
        contract = publication.contract
        contract_data = {
            "title": title,
            "winner_name": contract.winning_publisher.name,
            "issue_date": (
                contract.issue_date.strftime("%d/%m/%Y")
                if contract.issue_date
                else "Niet van toepassing"
            ),
            "contracting_authority": (
                contract.contracting_authority.name
                if contract.contracting_authority
                else "Niet van toepassing"
            ),
        }

        # Load template from external file
        template_path = Path(__file__).parent / "contract_win_email.html"
        with open(template_path, "r", encoding="utf-8") as f:
            template_content = f.read()

        # Use Template class for safer substitution
        template = Template(template_content)
        return template.safe_substitute(contract_data)

    async def _send_email(
        self, recipient_email: str, recipient_name: str, subject: str, content: str
    ) -> bool:
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

    async def _track_email(
        self,
        contract: Contract,
        recipient_email: str,
        recipient_name: str,
        subject: str,
        content: str,
        is_delivered: bool,
        session: Session,
        delivery_error: Optional[str] = None,
    ):
        """Track sent email in database"""
        try:
            email_tracking = ContractEmailTracking(
                contract_id=contract.contract_id,
                recipient_email=recipient_email,
                recipient_name=recipient_name,
                email_subject=subject,
                email_content=content,
                is_delivered=is_delivered,
                delivery_error=delivery_error,
            )

            session.add(email_tracking)
            session.commit()

            logging.info(f"Email tracking recorded for contract {contract.contract_id}")

        except Exception as e:
            logging.error(f"Error tracking email: {e}")
            session.rollback()
