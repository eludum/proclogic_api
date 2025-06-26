import logging
from contextlib import contextmanager
from typing import Optional

import requests
from clerk_backend_api import Clerk
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwk, jwt
from jose.exceptions import JWTError
from pydantic import BaseModel

import app.crud.company as crud_company
from app.config.postgres import get_session
from app.config.settings import Settings

settings = Settings()
security = HTTPBearer()

# JWKS cache
_jwks_cache = None


class AuthUser(BaseModel):
    user_id: str
    email: Optional[str] = None
    has_valid_subscription: bool = False
    subscription_status: str = "inactive"
    company_vat_number: Optional[str] = None


def get_jwks():
    """Get the JSON Web Key Set from Clerk"""
    global _jwks_cache
    if _jwks_cache is None:
        logging.info("Fetching JWKS from Clerk")
        response = requests.get(settings.clerk_jwks_url)
        if response.status_code != 200:
            logging.error(f"Failed to get JWKS: {response.status_code}")
            raise HTTPException(
                status_code=500, detail="Failed to get authentication keys"
            )
        _jwks_cache = response.json()
    return _jwks_cache


def get_public_key(kid):
    """Get the public key for a specific key ID"""
    jwks = get_jwks()
    for key in jwks["keys"]:
        if key["kid"] == kid:
            return jwk.construct(key)
    logging.error(f"No key found for kid: {kid}")
    raise HTTPException(status_code=401, detail="Invalid token")


def decode_token(token: str):
    """Decode and verify the JWT token"""
    try:
        # Get the key ID from the token headers
        headers = jwt.get_unverified_headers(token)
        kid = headers.get("kid")
        if not kid:
            logging.error("No kid found in token headers")
            raise HTTPException(status_code=401, detail="Invalid token format")

        # Get the public key
        public_key = get_public_key(kid)

        # Decode and verify the token
        return jwt.decode(
            token,
            public_key.to_pem().decode("utf-8"),
            algorithms=["RS256"],
        )
    except JWTError as e:
        logging.error(f"JWT Error: {str(e)}")
        raise HTTPException(
            status_code=401, detail=f"Token verification failed: {str(e)}"
        )
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=401, detail="Authentication failed")


@contextmanager
def get_clerk_client():
    """Context manager for Clerk client to ensure proper cleanup"""
    with Clerk(bearer_auth=settings.clerk_secret_key) as clerk:
        yield clerk


async def get_auth_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Authenticate the user and return their user information with subscription status"""
    token = credentials.credentials
    payload = decode_token(token)

    # Extract user ID from the token payload
    user_id = payload.get("sub")
    if not user_id:
        logging.error("No user ID found in token payload")
        raise HTTPException(status_code=401, detail="User ID not found in token")

    # Get additional user details from Clerk
    try:
        with get_clerk_client() as clerk:
            user = clerk.users.get(user_id=user_id)
            if not user:
                logging.error(f"User not found in Clerk: {user_id}")
                raise HTTPException(status_code=404, detail="User not found")

            # Get primary email
            email = None
            if user.email_addresses and len(user.email_addresses) > 0:
                for email_obj in user.email_addresses:
                    if getattr(email_obj, "primary", False):
                        email = email_obj.email_address
                        break
                if not email and user.email_addresses:
                    # Fallback to first email if no primary is marked
                    email = user.email_addresses[0].email_address

            # Ensure we have an email
            if not email:
                logging.error(f"No email found for user: {user_id}")
                raise HTTPException(status_code=400, detail="User email not available")

            # Check subscription status in database
            with get_session() as session:
                company = crud_company.get_company_by_email(
                    email=email, session=session
                )

                if not company:
                    # No company found - user needs to complete onboarding or start trial
                    return AuthUser(
                        user_id=user_id,
                        email=email,
                        has_valid_subscription=False,
                        subscription_status="no_company",
                    )

                # Check if subscription is valid (paid or trial)
                has_valid_subscription = company.has_valid_subscription

                # Update trial status if expired
                if company.is_trial_active and company.is_trial_expired:
                    company.end_trial()
                    session.commit()
                    has_valid_subscription = False

                return AuthUser(
                    user_id=user_id,
                    email=email,
                    has_valid_subscription=has_valid_subscription,
                    subscription_status=company.subscription_status,
                    company_vat_number=company.vat_number,
                )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logging.error(f"Error retrieving user data from Clerk: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user email")


async def get_auth_user_with_subscription_check(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Enhanced auth function that requires valid subscription.
    Use this for protected endpoints that require paid access.
    """
    auth_user = await get_auth_user(credentials)

    if not auth_user.has_valid_subscription:
        if auth_user.subscription_status == "no_company":
            raise HTTPException(
                status_code=403, detail="Please complete company onboarding first"
            )
        elif (
            auth_user.subscription_status == "trial"
            and auth_user.has_valid_subscription == False
        ):
            raise HTTPException(
                status_code=403,
                detail="Trial period has expired. Please upgrade to continue.",
            )
        else:
            raise HTTPException(
                status_code=403,
                detail="Active subscription required to access this feature",
            )

    return auth_user
