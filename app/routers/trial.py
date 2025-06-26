# app/routers/trial.py
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.config.postgres import get_session
from app.crud.trial import (
    check_and_update_expired_trials,
    create_trial_company_and_invite_user,
    get_trial_status,
    start_trial_for_existing_company,
)
from app.schemas.company_schemas import SubscriptionStatusResponse, TrialInviteRequest
from app.util.clerk import AuthUser, get_auth_user

trial_router = APIRouter()


class TrialStatusResponse(BaseModel):
    has_trial: bool
    is_active: bool = False
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    days_remaining: Optional[int] = None
    is_expired: bool = False
    subscription_status: str = "inactive"


@trial_router.post("/trial/invite", status_code=201)
async def invite_trial_user(
    trial_request: TrialInviteRequest
):
    """
    Create a trial company and invite a user.
    This endpoint can be used by admins or through a public signup form.
    """
    with get_session() as session:
        success = create_trial_company_and_invite_user(
            email=trial_request.email,
            company_name=trial_request.company_name,
            company_vat_number=trial_request.company_vat_number,
            summary_activities=trial_request.summary_activities,
            session=session,
        )

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Failed to create trial account. Company may already exist.",
            )

        return {
            "message": f"Trial account created and invitation sent to {trial_request.email}",
            "trial_days": 7,
        }


@trial_router.post("/trial/start")
async def start_trial(auth_user: AuthUser = Depends(get_auth_user)):
    """
    Start a trial for the authenticated user's company.
    """
    if not auth_user.company_vat_number:
        raise HTTPException(
            status_code=400, detail="No company associated with this user"
        )

    with get_session() as session:
        success = start_trial_for_existing_company(
            company_vat_number=auth_user.company_vat_number, session=session
        )

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Failed to start trial. Company may already have an active subscription or trial.",
            )

        return {"message": "Trial started successfully", "trial_days": 7}


@trial_router.get("/trial/status", response_model=TrialStatusResponse)
async def get_user_trial_status(auth_user: AuthUser = Depends(get_auth_user)):
    """
    Get trial status for the authenticated user's company.
    """
    if not auth_user.company_vat_number:
        raise HTTPException(
            status_code=400, detail="No company associated with this user"
        )

    with get_session() as session:
        status = get_trial_status(
            company_vat_number=auth_user.company_vat_number, session=session
        )

        if "error" in status:
            raise HTTPException(status_code=404, detail=status["error"])

        return TrialStatusResponse(**status)


@trial_router.get("/subscription/status", response_model=SubscriptionStatusResponse)
async def get_subscription_status(auth_user: AuthUser = Depends(get_auth_user)):
    """
    Get comprehensive subscription status for the authenticated user.
    This is the main endpoint to check if user has access to paid features.
    """
    if not auth_user.company_vat_number:
        return SubscriptionStatusResponse(
            has_access=False,
            subscription_status="no_company",
            message="Please complete company onboarding first",
        )

    with get_session() as session:
        trial_status = get_trial_status(
            company_vat_number=auth_user.company_vat_number, session=session
        )

        if "error" in trial_status:
            return SubscriptionStatusResponse(
                has_access=False,
                subscription_status="error",
                message=trial_status["error"],
            )

        # Determine access and message
        has_access = auth_user.has_valid_subscription
        message = ""
        trial_days_remaining = None
        trial_end_date = None

        if auth_user.subscription_status == "active":
            message = "Active subscription"
        elif auth_user.subscription_status == "trial":
            if has_access:
                trial_days_remaining = trial_status.get("days_remaining", 0)
                trial_end_date = trial_status.get("end_date")
                message = f"Trial active - {trial_days_remaining} days remaining"
            else:
                message = "Trial has expired. Please upgrade to continue."
        elif auth_user.subscription_status == "inactive":
            message = (
                "No active subscription. Start a trial or subscribe to access features."
            )
        elif auth_user.subscription_status == "cancelled":
            message = "Subscription cancelled. Please resubscribe to continue."
        else:
            message = "Unknown subscription status"

        return SubscriptionStatusResponse(
            has_access=has_access,
            subscription_status=auth_user.subscription_status,
            trial_days_remaining=trial_days_remaining,
            trial_end_date=trial_end_date,
            message=message,
        )


@trial_router.post("/admin/check-expired-trials")
async def check_expired_trials_admin():
    """
    Admin endpoint to manually check and update expired trials.
    In production, this should be called by a scheduled job.
    """
    with get_session() as session:
        expired_count = check_and_update_expired_trials(session)
        return {"message": f"Checked expired trials", "expired_count": expired_count}


def schedule_trial_expiration_check():
    """
    Background task to check for expired trials.
    This should be scheduled to run daily.
    """
    try:
        with get_session() as session:
            expired_count = check_and_update_expired_trials(session)
            logging.info(f"Background task: {expired_count} trials marked as expired")
    except Exception as e:
        logging.error(f"Error in background trial expiration check: {e}")


# Utility function for other modules
def verify_subscription_access(auth_user: AuthUser) -> bool:
    """
    Quick utility to verify if user has subscription access.
    Use this in other routers that need subscription checks.
    """
    return auth_user.has_valid_subscription
