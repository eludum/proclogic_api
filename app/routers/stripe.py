from app.config.settings import Settings
import stripe
from fastapi import APIRouter, Request, Header, HTTPException
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
            payload=payload,
            sig_header=stripe_signature,
            secret=endpoint_secret
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    session = event["data"]["object"]

    if event_type in ["checkout.session.completed", "checkout.session.async_payment_succeeded"]:
        await fulfill_checkout(session["id"])

    return JSONResponse(status_code=200, content={"status": "success"})

async def fulfill_checkout(session_id: str):
    try:
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=["line_items"]
        )
    except stripe.error.StripeError as e:
        # Handle error appropriately
        return

    if session.payment_status != "paid":
        # Payment not completed; no fulfillment
        return

    # TODO: Implement your fulfillment logic here
    # For example:
    # - Provision access to services
    # - Trigger shipment of goods
    # - Update inventory or stock records
    # - Send custom receipt emails
    # - Save payment details and line items to your database

    # Ensure idempotency: check if this session_id has already been fulfilled
    # to prevent duplicate processing

    return
