import logging
import stripe
from app.config.settings import Settings
from clerk_backend_api import Clerk, CreateInvitationRequestBody, CreateUserRequestBody
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

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
        print("Invalid payload")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        print("Invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    session = event["data"]["object"]

    if event_type in [
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    ]:
        await fulfill_checkout(session["id"])

    return JSONResponse(status_code=200, content={"status": "success"})


async def fulfill_checkout(session_id: str):
    try:
        session = stripe.checkout.Session.retrieve(session_id, expand=["line_items"])
    except stripe.error.StripeError as e:
        logging.error(f"Stripe error occurred: {e}")
        return

    if session.payment_status != "paid":
        # Payment not completed; no fulfillment
        return

    # Ensure idempotency: check if this session_id has already been fulfilled
    # to prevent duplicate processing

    with Clerk(bearer_auth=settings.clerk_secret_key) as clerk:
        invitations = clerk.invitations.list(query=session.customer_email)

        # Check if user has already been invited
        if invitations is not []:
            for invitation in invitations:
                if invitation.email_address == session.customer_email:
                    return

        # Create Clerk user
        invitation = clerk.invitations.create(
            request=CreateInvitationRequestBody(
                email_address=session.customer_email,
                # TODO: add subscription
                public_metadata={"onboardingComplete": False},
            )
        )

        if not invitation:
            logging.error(
                f"Failed to create Clerk invitation for {session.customer_email}"
            )
            return False

        # TODO: send custom receipt emails
        # - Save payment details and line items to your database

    return
