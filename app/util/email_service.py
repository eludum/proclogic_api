import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.ai.openai import get_openai_client
from app.models.email_models import ContractEmailTracking
from app.models.publication_contract_models import Contract


class ContractEmailService:
    """Service for sending automated emails to contract winners"""

    def __init__(self):
        self.openai_client = get_openai_client()
        self.smtp_server = "sandbox.smtp.mailtrap.io"
        self.smtp_port = 2525
        self.smtp_user = "44230b56ee39ca"
        self.smtp_password = "76cc41676b4f36"
        self.sender_email = "ProcLogic Team <team@proclogic.be>"

    async def send_contract_winner_email(
        self, contract: Contract, session: Session, custom_message: Optional[str] = None
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
            email_content = await self._generate_personalized_email(
                contract, custom_message
            )

            # Create email subject
            subject = f"Proficiat met uw contractwin! Ontdek hoe ProcLogic u kan helpen - {contract.notice_id}"

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

    async def _generate_personalized_email(
        self, contract: Contract, custom_message: Optional[str] = None
    ) -> str:
        """Generate personalized email content using OpenAI"""

        # Prepare contract data for personalization
        contract_data = {
            "notice_id": contract.notice_id,
            "contract_id": contract.contract_id,
            "winner_name": contract.winning_publisher.name,
            "winner_business_id": contract.winning_publisher.business_id,
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

        # Create prompt for OpenAI
        prompt = f"""
        Generate a professional and personalized congratulatory email to a company that just won a public contract. 
        The email should congratulate them and introduce ProcLogic as a procurement intelligence platform that can help them win more contracts.
        
        Company Details:
        - Company Name: {contract_data['winner_name']}
        - Business ID: {contract_data['winner_business_id']}
        
        Contract Details:
        - Notice ID: {contract_data['notice_id']}
        - Contract ID: {contract_data['contract_id']}
        - Contract Value: {contract_data['contract_amount']} {contract_data['currency']}
        - Issue Date: {contract_data['issue_date']}
        - Contracting Authority: {contract_data['contracting_authority']}
        - Notice Type: {contract_data['notice_type']}
        
        {"Custom message to include: " + custom_message if custom_message else ""}
        
        Requirements:
        - Start with genuine congratulations on their contract win
        - Mention specific contract details to show legitimacy
        - Introduce ProcLogic as Belgium's most advanced public procurement platform
        - Highlight key benefits: AI-powered recommendations, deadline reminders, advanced search, market insights
        - Mention that successful companies like theirs use ProcLogic to find more opportunities
        - Include a clear call-to-action to visit https://proclogic.be
        - Professional yet warm tone
        - Write in Dutch (as this is for Belgian market)
        - Format as HTML for better presentation
        - Keep it concise but compelling
        
        Generate the email body (HTML format) without subject line.
        """

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional email writer for ProcLogic, Belgium's leading procurement intelligence platform. Generate compelling, congratulatory emails that introduce ProcLogic's services to successful contract winners. Write in Dutch and focus on how ProcLogic can help them win more contracts.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1500,
                temperature=0.7,
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logging.error(f"Error generating email with OpenAI: {e}")
            # Fallback to template email
            return self._get_fallback_email_template(contract_data)

    def _get_fallback_email_template(self, contract_data: Dict[str, Any]) -> str:
        """Fallback email template if OpenAI fails"""
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2563eb;">Proficiat met uw contractwin!</h2>
                
                <p>Beste {contract_data['winner_name']},</p>
                
                <p>Van harte gefeliciteerd! Wij hebben genoteerd dat uw bedrijf het volgende contract heeft gewonnen:</p>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #2563eb; margin: 20px 0;">
                    <ul style="margin: 0; list-style-type: none; padding: 0;">
                        <li><strong>Notice ID:</strong> {contract_data['notice_id']}</li>
                        <li><strong>Contract ID:</strong> {contract_data['contract_id']}</li>
                        <li><strong>Contractwaarde:</strong> {contract_data['contract_amount']} {contract_data['currency']}</li>
                        <li><strong>Uitgiftedatum:</strong> {contract_data['issue_date']}</li>
                        <li><strong>Aanbestedende overheid:</strong> {contract_data['contracting_authority']}</li>
                    </ul>
                </div>
                
                <h3 style="color: #2563eb;">Ontdek meer kansen met ProcLogic</h3>
                
                <p>Succesvolle bedrijven zoals het uwe gebruiken <strong>ProcLogic</strong> - het meest geavanceerde publieke aanbestedingsplatform van België - om nog meer contracten te winnen.</p>
                
                <div style="background-color: #eff6ff; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h4 style="margin-top: 0; color: #1e40af;">Met ProcLogic krijgt u:</h4>
                    <ul style="color: #374151;">
                        <li>🤖 <strong>AI-aangedreven aanbevelingen</strong> - Vind automatisch aanbestedingen die perfect bij uw profiel passen</li>
                        <li>🔍 <strong>Geavanceerd zoeken</strong> - Ontdek precies de kansen die u zoekt</li>
                        <li>⏰ <strong>Deadline herinneringen</strong> - Mis nooit meer een belangrijke deadline</li>
                        <li>📊 <strong>Marktinzichten</strong> - Blijf op de hoogte van trends in uw sector</li>
                    </ul>
                </div>
                
                <p><strong>Klaar om meer contracten te winnen?</strong></p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="https://proclogic.be" 
                       style="background-color: #2563eb; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                        Ontdek ProcLogic →
                    </a>
                </div>
                
                <p style="color: #6b7280; font-size: 14px;">
                    Veel succes met de uitvoering van uw contract!<br>
                    <br>
                    Met vriendelijke groeten,<br>
                    <strong>Het ProcLogic Team</strong><br>
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
                server.login(self.smtp_user, self.smtp_password)
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
