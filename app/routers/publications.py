from typing import Annotated, List, Optional
from fastapi import APIRouter, HTTPException, Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, jwk
from jose.exceptions import JWTError
import requests
import logging
from clerk_backend_api import Clerk
from contextlib import contextmanager

from app.config.settings import Settings
from app.schemas.publication_out_schemas import PublicationOut
from app.config.postgres import get_session
import app.crud.company as crud_company
import app.crud.publication as crud_publication
from app.crud.mapper import (
    convert_publications_to_out_schema_list_paid,
    convert_publication_to_out_schema_details_paid,
    convert_publications_to_out_schema_list_free,
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = Settings()
publications_router = APIRouter()
security = HTTPBearer()

# Clerk configuration
clerk_issuer = "immune-pegasus-53.clerk.accounts.dev"
clerk_jwks_url = f"https://{clerk_issuer}/.well-known/jwks.json"

# JWKS cache
_jwks_cache = None


def get_jwks():
    """Get the JSON Web Key Set from Clerk"""
    global _jwks_cache
    if _jwks_cache is None:
        logger.info("Fetching JWKS from Clerk")
        response = requests.get(clerk_jwks_url)
        if response.status_code != 200:
            logger.error(f"Failed to get JWKS: {response.status_code}")
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
    logger.error(f"No key found for kid: {kid}")
    raise HTTPException(status_code=401, detail="Invalid token")


def decode_token(token: str):
    """Decode and verify the JWT token"""
    try:
        # Get the key ID from the token headers
        headers = jwt.get_unverified_headers(token)
        kid = headers.get("kid")
        if not kid:
            logger.error("No kid found in token headers")
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
        logger.error(f"JWT Error: {str(e)}")
        raise HTTPException(
            status_code=401, detail=f"Token verification failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=401, detail="Authentication failed")


@contextmanager
def get_clerk_client():
    """Context manager for Clerk client to ensure proper cleanup"""
    with Clerk(bearer_auth=settings.clerk_secret_key) as clerk:
        yield clerk


class AuthUser:
    """Class to hold authenticated user information"""

    def __init__(self, user_id: str, email: Optional[str] = None):
        self.user_id = user_id
        self.email = email


async def get_auth_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Authenticate the user and return their user information"""
    token = credentials.credentials
    payload = decode_token(token)

    # Extract user ID from the token payload
    user_id = payload.get("sub")
    if not user_id:
        logger.error("No user ID found in token payload")
        raise HTTPException(status_code=401, detail="User ID not found in token")

    # Get additional user details from Clerk
    try:
        with get_clerk_client() as clerk:
            user = clerk.users.get(user_id=user_id)
            if not user:
                logger.error(f"User not found in Clerk: {user_id}")
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

            return AuthUser(user_id=user_id, email=email)
    except Exception as e:
        logger.error(f"Error retrieving user data from Clerk: {str(e)}")
        # We still have a valid token, so we can return basic user info
        return AuthUser(user_id=user_id)


# Use this as a drop-in replacement for previous require_auth function
require_auth = get_auth_user


@publications_router.get("/publications/", response_model=List[PublicationOut])
async def get_publications(auth_user: AuthUser = Depends(get_auth_user)):
    """Get all publications for an authenticated user"""
    logger.info(f"Fetching publications for user: {auth_user.user_id}")

    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        publications = crud_publication.get_all_publications(session=session)

        return [
            convert_publications_to_out_schema_list_paid(
                publication=publication, company=company
            )
            for publication in publications
        ]


@publications_router.get(
    "/publications/publication/{publication_workspace_id}/",
    response_model=PublicationOut,
)
async def get_publication_by_workspace_id(
    publication_workspace_id: str,
    auth_user: AuthUser = Depends(require_auth),
) -> PublicationOut:
    """Get a specific publication by workspace ID"""
    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        publication = crud_publication.get_publication_by_workspace_id(
            publication_workspace_id=publication_workspace_id, session=session
        )

        if not publication:
            raise HTTPException(status_code=404, detail="Publication not found")

        return convert_publication_to_out_schema_details_paid(
            publication=publication, company=company
        )


@publications_router.get(
    "/publications/free/search/{search_term}/",
    response_model=List[PublicationOut],
)
async def search_publications_free(
    search_term: str,
) -> List[PublicationOut]:
    """Search publications without authentication"""
    # TODO: add extra filters like region and cpv
    with get_session() as session:
        if not search_term:
            publications = crud_publication.get_all_publications(session=session)
            return [
                convert_publications_to_out_schema_list_free(publication=publication)
                for publication in publications
            ]
        else:
            publications = crud_publication.search_publications(
                search_term=search_term, session=session
            )

            return [
                convert_publications_to_out_schema_list_free(publication=publication)
                for publication in publications
            ]
