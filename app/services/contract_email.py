import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.publication_contract_models import Contract
from app.util.email_service import ContractEmailService
from app.ai.openai import get_openai_client

async def handle_new_contract_created(
    contract: Contract, session: Session, custom_message: Optional[str] = None
):
    """
    Handle new contract creation - send automatic email to winner

    This should be called whenever a new contract is created in your system.
    """
    try:
        # Initialize email service
        email_service = ContractEmailService()

        # Send email to contract winner
        success = await email_service.send_contract_winner_email(
            contract=contract, session=session, custom_message=custom_message
        )

        if success:
            logging.info(
                f"Contract winner email sent successfully for contract {contract.contract_id}"
            )
        else:
            logging.warning(
                f"Failed to send contract winner email for contract {contract.contract_id}"
            )

    except Exception as e:
        logging.error(f"Error handling new contract created: {e}")
