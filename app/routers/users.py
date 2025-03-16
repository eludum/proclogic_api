from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query

import app.crud.company as crud_company
import app.crud.company_user as crud_company_user
from app.config.postgres import get_session
from app.util.clerk import AuthUser, get_auth_user
from pydantic import BaseModel, EmailStr

users_router = APIRouter()


class UserResponse(BaseModel):
    id: Optional[str] = None
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    created_at: Optional[str] = None
    last_sign_in_at: Optional[str] = None
    status: str


class AddUserRequest(BaseModel):
    email: EmailStr


@users_router.get("/users/company-emails")
async def get_company_emails(auth_user: AuthUser = Depends(get_auth_user)):
    """Get all authorized email addresses for the company associated with the authenticated user."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Return the emails
        return {"emails": company.emails}


@users_router.post("/users/invite", status_code=201)
async def invite_user_to_company(
    user: AddUserRequest,
    auth_user: AuthUser = Depends(get_auth_user)
):
    """Invite a new user to the company by sending a Clerk invitation."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Add and invite user
        success = crud_company_user.add_user_to_company(
            company_vat_number=company.vat_number,
            email=user.email,
            session=session
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to invite user to company")

        return {"message": f"User {user.email} invited successfully", "emails": company.emails}


@users_router.delete("/users/remove/{email}")
async def remove_user_from_company(
    email: str = Path(..., description="Email to remove"),
    user_id: Optional[str] = Query(None, description="Clerk user ID if available"),
    auth_user: AuthUser = Depends(get_auth_user)
):
    """Remove a user from the company and optionally delete their Clerk account."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")
        
    # Prevent removing the authenticated user's email
    if email == auth_user.email:
        raise HTTPException(status_code=400, detail="Cannot remove your own account")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Remove user from company
        success = crud_company_user.remove_user_from_company(
            company_vat_number=company.vat_number,
            email=email,
            user_id=user_id,
            session=session
        )

        if not success:
            raise HTTPException(
                status_code=400, 
                detail="Failed to remove user. Make sure it's not the last user or doesn't exist."
            )

        return {"message": f"User {email} removed successfully"}


@users_router.get("/users/company-users", response_model=List[UserResponse])
async def get_company_users(auth_user: AuthUser = Depends(get_auth_user)):
    """Get all users that have access to the company, including pending invitations."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Get users with complete Clerk information
        users = crud_company_user.get_company_users(
            company_vat_number=company.vat_number,
            session=session
        )

        return users