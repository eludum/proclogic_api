from typing import Optional
from fastapi import HTTPException, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, jwk
from jose.exceptions import JWTError
from pydantic import BaseModel
import requests
import logging
from clerk_backend_api import Clerk
from contextlib import contextmanager

from app.config.settings import Settings

settings = Settings()
security = HTTPBearer()

# JWKS cache
_jwks_cache = None


class AuthUser(BaseModel):
    user_id: str
    email: Optional[str] = None


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
    """Authenticate the user and return their user information"""
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

            # Return with user_id and email
            return AuthUser(user_id=user_id, email=email)

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logging.error(f"Error retrieving user data from Clerk: {str(e)}")
        # Don't return a user without an email
        raise HTTPException(status_code=500, detail="Failed to retrieve user email")
