from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.email_models import ContractEmailTracking


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
