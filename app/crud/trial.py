import logging
from datetime import datetime, timedelta

from clerk_backend_api import Clerk, CreateInvitationRequestBody
from sqlalchemy.orm import Session

import app.crud.company as crud_company
from app.config.settings import Settings
from app.models.company_models import Company
from app.util.email.trial_email_service import TrialEmailService

settings = Settings()


def create_trial_company_and_invite_user(
    email: str,
    company_name: str,
    company_vat_number: str,
    summary_activities: str,
    session: Session,
    trial_days: int = 7,
) -> bool:
    """
    Create a new company with trial access and invite user via Clerk.

    Args:
        email: User's email address
        company_name: Name of the company
        company_vat_number: VAT number for the company
        summary_activities: Description of company activities
        session: Database session
        trial_days: Number of trial days (default: 7)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Check if company already exists
        existing_company = crud_company.get_company_by_vat_number(
            vat_number=company_vat_number, session=session
        )

        if existing_company:
            logging.warning(f"Company with VAT {company_vat_number} already exists")
            return False

        # Create trial company
        now = datetime.now()
        trial_end = now + timedelta(days=trial_days)

        new_company = Company(
            vat_number=company_vat_number,
            name=company_name,
            emails=[email],
            subscription="starter",  # Default subscription type
            summary_activities=summary_activities,
            trial_start_date=now,
            trial_end_date=trial_end,
            is_trial_active=True,
            subscription_status="trial",
        )

        session.add(new_company)
        session.flush()  # Get the company ID

        # Create Clerk invitation with trial metadata
        with Clerk(bearer_auth=settings.clerk_secret_key) as clerk:
            invitation = clerk.invitations.create(
                request=CreateInvitationRequestBody(
                    email_address=email,
                    public_metadata={
                        "onboardingComplete": False,  # They'll need to complete onboarding
                        "trialAccount": True,
                        "trialEndDate": trial_end.isoformat(),
                        "companyVatNumber": company_vat_number,
                    },
                )
            )

            if not invitation:
                logging.error(f"Failed to create Clerk invitation for {email}")
                session.rollback()
                return False
        
        try:
            TrialEmailService().send_trial_welcome_email(
                email=new_company.emails[0],
                company_name=new_company.name,
                trial_end_date=trial_end.strftime("%d/%m/%Y")
            )
            logging.info(f"Welcome email sent to {new_company.emails[0]}")
        except Exception as e:
            logging.error(f"Failed to send welcome email: {e}")

        session.commit()
        logging.info(f"Created trial company {company_vat_number} and invited {email}")
        return True

    except Exception as e:
        logging.error(f"Error creating trial company and inviting user: {e}")
        session.rollback()
        return False


def start_trial_for_existing_company(
    company_vat_number: str, session: Session, trial_days: int = 7
) -> bool:
    """
    Start trial for an existing company.

    Args:
        company_vat_number: VAT number of the company
        session: Database session
        trial_days: Number of trial days

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        company = crud_company.get_company_by_vat_number(
            vat_number=company_vat_number, session=session
        )

        if not company:
            logging.error(f"Company {company_vat_number} not found")
            return False

        # Don't start trial if already has active subscription
        if company.subscription_status == "active":
            logging.warning(
                f"Company {company_vat_number} already has active subscription"
            )
            return False

        # Don't start trial if already had one (optional business rule)
        if company.trial_start_date:
            logging.warning(f"Company {company_vat_number} already had a trial")
            return False

        company.start_trial(trial_days)
        session.commit()

        logging.info(f"Started trial for company {company_vat_number}")
        return True

    except Exception as e:
        logging.error(f"Error starting trial for company {company_vat_number}: {e}")
        session.rollback()
        return False


def check_and_update_expired_trials(session: Session) -> int:
    """
    Check for expired trials and update their status.
    This should be run periodically (e.g., daily cron job).

    Returns:
        int: Number of trials that were marked as expired
    """
    try:
        now = datetime.now()

        # Find companies with expired trials
        expired_trials = (
            session.query(Company)
            .filter(Company.is_trial_active == True, Company.trial_end_date <= now)
            .all()
        )

        count = 0
        for company in expired_trials:
            company.end_trial()
            count += 1

        session.commit()
        logging.info(f"Marked {count} trials as expired")
        return count

    except Exception as e:
        logging.error(f"Error checking expired trials: {e}")
        session.rollback()
        return 0


def get_trial_status(company_vat_number: str, session: Session) -> dict:
    """
    Get detailed trial status for a company.

    Returns:
        dict: Trial status information
    """
    try:
        company = crud_company.get_company_by_vat_number(
            vat_number=company_vat_number, session=session
        )

        if not company:
            return {"error": "Company not found"}

        if not company.trial_start_date:
            return {"has_trial": False, "message": "No trial started"}

        now = datetime.now()
        days_remaining = None

        if company.trial_end_date:
            days_remaining = max(0, (company.trial_end_date - now).days)

        return {
            "has_trial": True,
            "is_active": company.is_trial_active,
            "start_date": company.trial_start_date,
            "end_date": company.trial_end_date,
            "days_remaining": days_remaining,
            "is_expired": company.is_trial_expired,
            "subscription_status": company.subscription_status,
        }

    except Exception as e:
        logging.error(f"Error getting trial status: {e}")
        return {"error": str(e)}
