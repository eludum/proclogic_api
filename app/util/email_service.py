import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.ai.openai import get_openai_client
from app.config.settings import Settings
from app.models.email_models import ContractEmailTracking
from app.models.publication_contract_models import Contract
from app.models.publication_models import Publication
from app.util.publication_utils.publication_converter import PublicationConverter

settings = Settings()


class ContractEmailService:
    """Service for sending automated emails to contract winners"""

    def __init__(self):
        self.openai_client = get_openai_client()
        self.smtp_server = "sandbox.smtp.mailtrap.io"
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

        try:
            # Generate personalized email content using OpenAI
            email_content = await self._get_email_template(publication=publication)

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

    # TODO: run mail through claude one last time
    def _get_email_template(self, publication: Publication) -> str:
        """Fallback email template if OpenAI fails"""
        # Prepare contract data for personalization
        pub_out = PublicationConverter.to_output_schema(publication=publication)
        contract = publication.contract
        contract_data = {
            "title": pub_out.title,
            "winner_name": contract.winning_publisher.name,
            "contract_amount": contract.total_contract_amount,
            "currency": contract.currency,
            "issue_date": (
                contract.issue_date.strftime("%Y-%m-%d")
                if contract.issue_date
                else "N/A"
            ),
            "contracting_authority": (
                contract.contracting_authority.name
                if contract.contracting_authority
                else "N/A"
            ),
            "notice_type": contract.notice_type,
        }
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2563eb;">Proficiat met uw contractwin!</h2>
                
                <p>Beste {contract_data['winner_name']},</p>
                
                <p>Van harte gefeliciteerd met het binnenhalen van de volgende gunning:</p>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #2563eb; margin: 20px 0;">
                    <ul style="margin: 0; list-style-type: none; padding: 0;">
                        <li><strong>Titel:</strong> {contract_data['title']}</li>
                        <li><strong>Uitgiftedatum:</strong> {contract_data['issue_date']}</li>
                        <li><strong>Aanbestedende overheid:</strong> {contract_data['contracting_authority']}</li>
                    </ul>
                </div>
                
                <p>Wil je in de toekomst nog meer contracten winnen? <a href="https://proclogic.be" style="color: #2563eb;">ProcLogic</a> helpt je daarbij. 
                Met onze slimme AI-tool vind, analyseer en selecteer je razendsnel de aanbestedingen die écht bij je bedrijf passen. Geen tijdverlies, wel direct overzicht.</p>              
                <div style="background-color: #eff6ff; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h4 style="margin-top: 0; color: #1e40af;">Wat kan je verwachten van ProcLogic?</h4>
                    <ul style="color: #374151;">
                        <li>Gepersonaliseerde aanbevelingen die aansluiten op je profiel/li>
                        <li>Je AI-assistent Procy, die 24/7 voor je klaarstaat</li>
                        <li>Concurrentieanalyse: zie wie er meedingt op vergelijkbare projecten</li>
                        <li>Automatische reminders zodat je nooit meer een deadline mist</li>
                    </ul>
                </div>
                
                <p><strong>Klaar om het maximale uit aanbestedingen te halen? Plan dan nu een gratis demo in. We laten je graag zien hoe ProcLogic werkt en wat het voor jou kan betekenen:</strong></p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="https://calendly.com/koselogic-info/30min" 
                       style="background-color: #2563eb; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                        Boek een demo →
                    </a>
                </div>
                
                <p style="color: #6b7280; font-size: 14px;">
                    Op naar je volgende winst!<br>
                    <br>
                    Met vriendelijke groeten,<br>
                    <strong>Het ProcLogic Team</strong><br>
                    <a href="mailto:info@proclogic.be" style="color: #2563eb;">info@proclogic.be</a>
                    <a href="tel:+32489895836" style="color: #2563eb;">+32 4 89 89 58 36</a>
                    <a href="https://proclogic.be" style="color: #2563eb;">proclogic.be</a>
                </p>
            </div>
        </body>
        </html>
        """

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
