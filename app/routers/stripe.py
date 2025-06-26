import logging

import stripe
from clerk_backend_api import Clerk, CreateInvitationRequestBody
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

import app.crud.company as crud_company
from app.config.postgres import get_session
from app.config.settings import Settings

stripe_router = APIRouter()

settings = Settings()

stripe.api_key = settings.stripe_secret_key
endpoint_secret = settings.stripe_webhook_secret


@stripe_router.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=stripe_signature, secret=endpoint_secret
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]

    if event_type in [
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    ]:
        session = event["data"]["object"]
        await fulfill_checkout(session["id"])

    elif event_type == "invoice.payment_succeeded":
        invoice = event["data"]["object"]
        await handle_successful_payment(invoice)

    elif event_type == "invoice.payment_failed":
        invoice = event["data"]["object"]
        await handle_failed_payment(invoice)

    elif event_type == "customer.subscription.updated":
        subscription = event["data"]["object"]
        await handle_subscription_update(subscription)

    elif event_type == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        await handle_subscription_cancellation(subscription)

    return JSONResponse(status_code=200, content={"status": "success"})


async def fulfill_checkout(session_id: str):
    """Handle successful checkout session completion"""
    try:
        session = stripe.checkout.Session.retrieve(
            session_id, expand=["line_items", "subscription"]
        )
    except stripe.error.StripeError as e:
        logging.error(f"Stripe error occurred: {e}")
        return

    if session.payment_status != "paid":
        return

    customer_email = session.customer_details.email
    customer_id = session.customer
    subscription_id = session.subscription

    # Check if this is a new user or existing trial user
    with get_session() as db_session:
        company = crud_company.get_company_by_email(
            email=customer_email, session=db_session
        )

        if company:
            # Existing company (possibly trial) - upgrade to paid
            await upgrade_trial_to_paid(
                company, customer_id, subscription_id, db_session
            )
        else:
            # New company - create with paid subscription
            await create_paid_company(
                customer_email, customer_id, subscription_id, session, db_session
            )


async def upgrade_trial_to_paid(
    company, customer_id: str, subscription_id: str, session
):
    """Upgrade a trial company to paid subscription"""
    try:
        # End trial and activate subscription
        company.is_trial_active = False
        company.subscription_status = "active"
        company.stripe_customer_id = customer_id
        company.stripe_subscription_id = subscription_id

        session.commit()
        logging.info(
            f"Upgraded company {company.vat_number} from trial to paid subscription"
        )

    except Exception as e:
        logging.error(f"Error upgrading trial to paid: {e}")
        session.rollback()


async def create_paid_company(
    customer_email: str,
    customer_id: str,
    subscription_id: str,
):
    """Create a new company with paid subscription and invite user"""
    try:
        with Clerk(bearer_auth=settings.clerk_secret_key) as clerk:
            # Create Clerk invitation for new paid user
            invitation = clerk.invitations.create(
                request=CreateInvitationRequestBody(
                    email_address=customer_email,
                    public_metadata={
                        "onboardingComplete": False,
                        "paidSubscription": True,
                        "stripeCustomerId": customer_id,
                        "stripeSubscriptionId": subscription_id,
                    },
                )
            )

            if not invitation:
                logging.error(f"Failed to create Clerk invitation for {customer_email}")
                return False

            logging.info(f"Created paid subscription for {customer_email}")

    except Exception as e:
        logging.error(f"Error creating paid company: {e}")


async def handle_successful_payment(invoice):
    """Handle successful recurring payment"""
    try:
        customer_id = invoice["customer"]

        with get_session() as session:
            company = crud_company.get_company_by_stripe_customer_id(
                customer_id=customer_id, session=session
            )

            if company:
                # Ensure subscription is active
                company.subscription_status = "active"
                session.commit()
                logging.info(f"Payment successful for company {company.vat_number}")

    except Exception as e:
        logging.error(f"Error handling successful payment: {e}")


async def handle_failed_payment(invoice):
    """Handle failed payment"""
    try:
        customer_id = invoice["customer"]

        with get_session() as session:
            company = crud_company.get_company_by_stripe_customer_id(
                customer_id=customer_id, session=session
            )

            if company:
                # Mark subscription as past due
                company.subscription_status = "past_due"
                session.commit()
                logging.warning(f"Payment failed for company {company.vat_number}")

    except Exception as e:
        logging.error(f"Error handling failed payment: {e}")


async def handle_subscription_update(subscription):
    """Handle subscription status changes"""
    try:
        customer_id = subscription["customer"]
        status = subscription["status"]

        with get_session() as session:
            company = crud_company.get_company_by_stripe_customer_id(
                customer_id=customer_id, session=session
            )

            if company:
                # Map Stripe status to our subscription status
                if status == "active":
                    company.subscription_status = "active"
                elif status in ["past_due", "unpaid"]:
                    company.subscription_status = "past_due"
                elif status == "canceled":
                    company.subscription_status = "cancelled"
                elif status == "incomplete":
                    company.subscription_status = "inactive"

                session.commit()
                logging.info(
                    f"Updated subscription status for company {company.vat_number} to {status}"
                )

    except Exception as e:
        logging.error(f"Error handling subscription update: {e}")


async def handle_subscription_cancellation(subscription):
    """Handle subscription cancellation"""
    try:
        customer_id = subscription["customer"]

        with get_session() as session:
            company = crud_company.get_company_by_stripe_customer_id(
                customer_id=customer_id, session=session
            )

            if company:
                company.subscription_status = "cancelled"
                company.stripe_subscription_id = None
                session.commit()
                logging.info(f"Subscription cancelled for company {company.vat_number}")

    except Exception as e:
        logging.error(f"Error handling subscription cancellation: {e}")
