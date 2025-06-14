from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.email_models import ContractEmailTracking
from app.schemas.email_schemas import EmailTrackingCreate


def create_email_tracking(
    email_data: EmailTrackingCreate, session: Session
) -> ContractEmailTracking:
    """Create new email tracking record"""
    email_tracking = ContractEmailTracking(**email_data.model_dump())
    session.add(email_tracking)
    session.commit()
    session.refresh(email_tracking)
    return email_tracking


def get_email_tracking_by_contract(
    contract_id: str, session: Session
) -> List[ContractEmailTracking]:
    """Get all email tracking records for a specific contract"""
    return (
        session.query(ContractEmailTracking)
        .filter(ContractEmailTracking.contract_id == contract_id)
        .order_by(desc(ContractEmailTracking.sent_at))
        .all()
    )
