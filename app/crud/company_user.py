import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from clerk_backend_api import Clerk, CreateInvitationRequestBody, GetUserListRequest
from sqlalchemy.orm import Session

import app.crud.company as crud_company
from app.config.settings import settings


def check_user_company_access(email: str, session: Session) -> Optional[str]:
    """
    Check if a user has access to a company based on their email.
    Returns the company VAT number if the user has access, None otherwise.
    """
    try:
        # Get company by email
        company = crud_company.get_company_by_email(email=email, session=session)
        if not company:
            return None

        return company.vat_number
    except Exception as e:
        logging.error(f"Error checking user company access: {e}")
        return None


def add_user_to_company(company_vat_number: str, email: str, session: Session) -> bool:
    """
    Add a user to a company by sending a Clerk invitation and adding the email
    to the company's authorized emails.
    """
    try:
        company = crud_company.get_company_by_vat_number(
            vat_number=company_vat_number, session=session
        )

        if not company:
            return False

        # Check if email already exists
        if email in company.emails:
            return True

        # Create Clerk invitation
        with Clerk(bearer_auth=settings.clerk_secret_key) as clerk:
            invitation = clerk.invitations.create(
                request=CreateInvitationRequestBody(
                    email_address=email, public_metadata={"onboardingComplete": True}
                )
            )

            if not invitation:
                logging.error(f"Failed to create Clerk invitation for {email}")
                return False

            # Add email to company
            # TODO: email not actually addede wtf
            crud_company.append_emails_to_company(
                vat_number=company_vat_number, emails=[email], session=session
            )
            session.commit()
            return True

    except Exception as e:
        logging.error(f"Error adding user to company: {e}")
        session.rollback()
        return False


def remove_user_from_company(
    company_vat_number: str, email: str, session: Session
) -> bool:
    """
    Remove a user from a company by deleting the Clerk user and removing the email
    from the company's authorized emails.
    """
    try:
        company = crud_company.get_company_by_vat_number(
            vat_number=company_vat_number, session=session
        )

        if not company:
            return False

        # Check if email exists
        if email not in company.emails:
            return False

        # Make sure at least one email remains
        if len(company.emails) <= 1:
            return False

        # Remove from Clerk if user_id is provided
        try:
            with Clerk(bearer_auth=settings.clerk_secret_key) as clerk:
                clerk_users = clerk.users.list(
                    request=GetUserListRequest(email_address=[email]),
                )
                if clerk_users != []:
                    user_id = clerk_users[0].id
                    clerk.users.delete(user_id=user_id)
        except Exception as clerk_error:
            logging.error(f"Error removing user from Clerk: {clerk_error}")
            # Continue anyway to remove from company

        # Remove email from company
        crud_company.remove_email_from_company(
            vat_number=company_vat_number, delete_email=email, session=session
        )
        session.commit()
        return True
    except Exception as e:
        logging.error(f"Error removing user from company: {e}")
        session.rollback()
        return False


def get_company_users(
    company_vat_number: str, session: Session
) -> List[Dict[str, Any]]:
    """
    Get all authorized users for a company with details from Clerk.
    """
    try:
        company = crud_company.get_company_by_vat_number(
            vat_number=company_vat_number, session=session
        )

        if not company:
            return []

        users = []

        # Get user details from Clerk
        with Clerk(bearer_auth=settings.clerk_secret_key) as clerk:
            for email in company.emails:
                try:
                    # Search for users with this email
                    clerk_users = clerk.users.list(
                        request=GetUserListRequest(email_address=[email]),
                    )

                    if clerk_users != []:
                        # User exists in Clerk
                        for user in clerk_users:
                            users.append(
                                {
                                    "id": user.id,
                                    "email": user.email_addresses[0].email_address,
                                    "first_name": user.first_name,
                                    "last_name": user.last_name,
                                    "created_at": datetime.fromtimestamp(
                                        user.created_at / 1000
                                    ).strftime("%m/%d/%Y, %H:%M:%S"),
                                    "last_sign_in_at": datetime.fromtimestamp(
                                        user.last_sign_in_at / 1000
                                    ).strftime("%m/%d/%Y, %H:%M:%S"),
                                    "status": "active",
                                }
                            )

                    else:
                        # User invited but not yet registered
                        # Check if there's a pending invitation
                        invitations = clerk.invitations.list(query=email)

                        if invitations is not []:
                            for invitation in invitations:
                                users.append(
                                    {
                                        "id": None,
                                        "email": email,
                                        "first_name": None,
                                        "last_name": None,
                                        "created_at": datetime.fromtimestamp(
                                            invitation.created_at / 1000
                                        ).strftime("%m/%d/%Y, %H:%M:%S"),
                                        "last_sign_in_at": None,
                                        "status": "invited",
                                    }
                                )

                except Exception as e:
                    logging.error(f"Error getting Clerk data for {email}: {e}")
                    # Add basic info even if Clerk lookup fails
                    users.append(
                        {
                            "id": None,
                            "email": email,
                            "first_name": None,
                            "last_name": None,
                            "created_at": None,
                            "last_sign_in_at": None,
                            "status": "error",
                        }
                    )

        return users
    except Exception as e:
        logging.error(f"Error getting company users: {e}")
        return []
