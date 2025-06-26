import asyncio
import logging
from datetime import datetime
from typing import List

from app.config.postgres import get_session
from app.crud.trial import check_and_update_expired_trials
from app.crud.company import get_companies_trial_expiring_soon
from app.models.company_models import Company
from app.util.email.trial_email_service import TrialEmailService


def check_trial_status() -> None:
    logging.info("Trial expiration check service")
    while True:
        try:
            try:
                await run_daily_trial_checks()
            except Exception as e:
                logging.error("Error in daily trail checks: %s", e)

            # Wait until next run
            await asyncio.sleep(86400)  # 1 day in seconds

        except asyncio.CancelledError:
            raise  # Re-raise to allow proper cleanup


def run_daily_trial_checks():
    """
    Main function to run daily trial expiration checks and notifications.
    Call this from your task scheduler (e.g., celery, cron, etc.)
    """
    logging.info("Starting daily trial expiration checks...")

    try:
        with get_session() as session:
            # 1. Check and mark expired trials
            expired_count = check_and_update_expired_trials(session)
            logging.info(f"Marked {expired_count} trials as expired")

            # 2. Send warning emails for trials expiring in 2 days
            expiring_soon = get_companies_trial_expiring_soon(2, session)
            send_expiring_notifications(expiring_soon)

            # 3. Send warning emails for trials expiring in 1 day
            expiring_tomorrow = get_companies_trial_expiring_soon(1, session)
            send_expiring_notifications(expiring_tomorrow, urgent=True)

            logging.info("Daily trial checks completed successfully")

    except Exception as e:
        logging.error(f"Error in daily trial checks: {e}")
        raise


def send_expiring_notifications(companies: List[Company], urgent: bool = False):
    """Send email notifications for trials expiring soon."""
    for company in companies:
        try:
            if not company.emails:
                continue

            primary_email = company.emails[0]  # Use first email as primary
            days_remaining = (company.trial_end_date - datetime.utcnow()).days

            # Send email notification
            TrialEmailService().send_trial_expiring_email(
                email=primary_email,
                company_name=company.name,
                days_remaining=days_remaining,
            )

            logging.info(f"Sent trial expiring notification to {primary_email}")

        except Exception as e:
            logging.error(f"Error sending notification to {company.vat_number}: {e}")


def send_expired_notifications(companies: List[Company]):
    """Send email notifications for expired trials."""
    for company in companies:
        try:
            if not company.emails:
                continue

            primary_email = company.emails[0]

            # Send expired trial email
            TrialEmailService.send_trial_expired_email(
                email=primary_email, company_name=company.name
            )

            logging.info(f"Sent trial expired notification to {primary_email}")

        except Exception as e:
            logging.error(
                f"Error sending expired notification to {company.vat_number}: {e}"
            )
