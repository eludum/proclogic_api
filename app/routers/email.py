from typing import List
from fastapi import APIRouter, Depends, HTTPException

import app.crud.email as crud_email
from app.config.postgres import get_session
from app.schemas.email_schemas import EmailTrackingResponse
from app.util.clerk import AuthUser, get_auth_user

email_tracking_router = APIRouter()


@email_tracking_router.get(
    "/email/contract/{contract_id}", response_model=List[EmailTrackingResponse]
)
async def get_contract_email_history(
    contract_id: str,
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Get email tracking history for a specific contract"""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        # Get email tracking records
        email_records = crud_email.get_email_tracking_by_contract(
            contract_id=contract_id, session=session
        )

        return [
            EmailTrackingResponse.model_validate(record) for record in email_records
        ]
    