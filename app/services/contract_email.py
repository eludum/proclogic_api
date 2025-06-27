import logging

from sqlalchemy.orm import Session

from app.models.publication_models import Publication
from app.util.email.email_service import ContractEmailService


async def handle_new_contract_created(publication: Publication, session: Session):
    """
    Handle new contract creation - send automatic email to winner

    This should be called whenever a new contract is created in your system.
    """
    try:
        # Initialize email service
        email_service = ContractEmailService()
        
        # Send email to contract winner
        success = await email_service.send_contract_winner_email(
            publication=publication, session=session
        )

        if success:
            logging.info(
                f"Contract winner email sent successfully for contract {publication.contract.contract_id}"
            )
        else:
            logging.warning(
                f"Failed to send contract winner email for contract {publication.contract.contract_id}"
            )

    except Exception as e:
        logging.error(f"Error handling new contract created: {e}")
