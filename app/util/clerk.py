from typing import Optional
from fastapi import HTTPException, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, jwk
from jose.exceptions import JWTError
from pydantic import BaseModel
import httpx
import logging
from clerk_backend_api import Clerk
from contextlib import contextmanager

from app.config.settings import settings


security = HTTPBearer()

# JWKS cache
_jwks_cache = None


class AuthUser(BaseModel):
    user_id: str
    email: Optional[str] = None


async def warm_jwks_cache():
    """Pre-warm JWKS cache at startup - call this from lifespan"""
    global _jwks_cache
    if _jwks_cache is None:
        try:
            logging.info("Pre-warming JWKS cache from Clerk")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(settings.clerk_jwks_url)
                if response.status_code == 200:
                    _jwks_cache = response.json()
                    logging.info("JWKS cache pre-warmed successfully")
                else:
                    logging.error(f"Failed to pre-warm JWKS: {response.status_code}")
        except Exception as e:
            logging.error(f"Error pre-warming JWKS cache: {str(e)}")


def get_jwks():
    """Get the JSON Web Key Set from Clerk (synchronous fallback)"""
    global _jwks_cache
    if _jwks_cache is None:
        logging.warning("JWKS cache miss - fetching synchronously (startup pre-warming may have failed)")
        import requests
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
    """Authenticate the user and return their user information with Redis caching"""
    from app.config.redis_manager import get_redis_client
    import pickle

    token = credentials.credentials
    payload = decode_token(token)

    # Extract user ID from the token payload
    user_id = payload.get("sub")
    if not user_id:
        logging.error("No user ID found in token payload")
        raise HTTPException(status_code=401, detail="User ID not found in token")

    # Try to get from Redis cache first
    redis_client = get_redis_client()
    cache_key = f"clerk:user:{user_id}"

    try:
        cached_user = redis_client.get(cache_key)
        if cached_user:
            user_data = pickle.loads(cached_user)
            return AuthUser(**user_data)
    except Exception as e:
        logging.warning(f"Redis cache read failed for user {user_id}: {str(e)}")

    # Cache miss - fetch from Clerk
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

            # Cache the result for 1 hour (3600 seconds)
            auth_user = AuthUser(user_id=user_id, email=email)
            try:
                redis_client.set(
                    cache_key,
                    pickle.dumps({"user_id": user_id, "email": email}),
                    ex=3600
                )
            except Exception as e:
                logging.warning(f"Redis cache write failed for user {user_id}: {str(e)}")

            return auth_user

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logging.error(f"Error retrieving user data from Clerk: {str(e)}")
        # Don't return a user without an email
        raise HTTPException(status_code=500, detail="Failed to retrieve user email")
