import asyncio
import json
import logging
from datetime import datetime, timedelta
import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import AnyHttpUrl, BaseModel

import app.crud.company as crud_company
from app.ai.openai import get_openai_client
from app.ai.recommend import get_recommendation
from app.ai.scraper import scrape_company_website
from app.config.postgres import get_session
from app.config.settings import Settings
from app.crud.mapper import convert_company_to_schema
from app.models.publication_models import CompanyPublicationMatch, Publication
from app.schemas.company_schemas import (
    CompanyPublicationMatchSchema,
    CompanySchema,
    CompanyUpdateSchema,
)
from app.util.clerk import AuthUser, get_auth_user
from app.util.messages_helper import send_recommendation_notification
from app.util.publication_utils.publication_converter import PublicationConverter

settings = Settings()

companies_router = APIRouter()


class WebsiteScrapingRequest(BaseModel):
    website_url: AnyHttpUrl


@companies_router.get("/company/", response_model=CompanySchema)
async def get_current_company(
    auth_user: AuthUser = Depends(get_auth_user),
) -> CompanySchema:
    """Get the company for the authenticated user by email."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        return await convert_company_to_schema(company)


@companies_router.get("/company/{vat_number}", response_model=CompanySchema)
async def get_company_by_vat_number(
    vat_number: str, auth_user: AuthUser = Depends(get_auth_user)
) -> CompanySchema:
    """Get a company by its VAT number. User must be authenticated."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        # Check if the user has access to this company (admin check or same company)
        user_company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not user_company or user_company.vat_number != vat_number:
            raise HTTPException(
                status_code=403, detail="Not authorized to access this company"
            )

        company = crud_company.get_company_by_vat_number(
            vat_number=vat_number, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        return await convert_company_to_schema(company)


@companies_router.post("/company/", response_model=CompanySchema)
async def create_company(
    company: CompanySchema,
    background_tasks: BackgroundTasks,
    auth_user: AuthUser = Depends(get_auth_user),
) -> CompanySchema:
    """Create a new company. User must be authenticated."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    # Ensure the company email includes the authenticated user's email
    if auth_user.email not in company.emails:
        company.emails.append(auth_user.email)

    with get_session() as session:
        # Check if the user already has a company
        existing_company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if existing_company:
            raise HTTPException(status_code=400, detail="User already has a company")

        created_company = crud_company.create_company(
            company_schema=company, session=session
        )
        if not created_company:
            raise HTTPException(status_code=500, detail="Failed to create company")

        # Add background task to generate recommendations
        # background_tasks.add_task(
        #     generate_recommendations_for_new_company,
        #     company_vat_number=created_company.vat_number
        # )

        return await convert_company_to_schema(created_company)


async def generate_recommendations_for_new_company(company_vat_number: str):
    """
    Background task to generate recommendations for a newly created company
    for all active publications from the past week.
    """
    logging.info(
        f"Starting background recommendation generation for company {company_vat_number}"
    )
    try:
        # Get publications from the past week
        one_week_ago = datetime.now() - timedelta(days=7)

        with get_session() as session:
            company = crud_company.get_company_by_vat_number(
                vat_number=company_vat_number, session=session
            )

            if not company:
                logging.error(
                    f"Company {company_vat_number} not found for recommendation generation"
                )
                return

            # Get active publications from the past week
            publications = (
                session.query(Publication)
                .filter(
                    Publication.publication_date >= one_week_ago,
                    Publication.vault_submission_deadline > datetime.now(),
                )
                .all()
            )

            logging.info(
                f"Found {len(publications)} recent publications for recommendation"
            )

            # Process each publication for recommendations
            for publication in publications:
                try:
                    # Generate recommendation
                    # TODO: fix that get_recommendation takes a db model instead of schema
                    match, match_percentage = get_recommendation(
                        publication=publication, company=company
                    )

                    if match:
                        # Create match record
                        match_schema = CompanyPublicationMatchSchema(
                            company_vat_number=company.vat_number,
                            publication_workspace_id=publication.publication_workspace_id,
                            match_percentage=float(match_percentage),
                            is_recommended=True,
                            is_saved=False,
                            is_viewed=False,
                        )

                        # Add to database
                        company_match = CompanyPublicationMatch(
                            company_vat_number=match_schema.company_vat_number,
                            publication_workspace_id=match_schema.publication_workspace_id,
                            match_percentage=match_schema.match_percentage,
                            is_recommended=match_schema.is_recommended,
                            is_saved=match_schema.is_saved,
                            is_viewed=match_schema.is_viewed,
                        )
                        session.add(company_match)

                        # Send notification asynchronously
                        asyncio.create_task(
                            send_recommendation_notification(
                                company_vat_number=company.vat_number,
                                publication_id=publication.publication_workspace_id,
                                publication_title=PublicationConverter.get_descr_as_str(
                                    publication.dossier.titles
                                ),
                                publication_submission_deadline=publication.vault_submission_deadline
                            )
                        )

                except Exception as e:
                    logging.error(
                        f"Error processing publication {publication.publication_workspace_id}: {e}"
                    )
                    continue

            # Commit all changes
            session.commit()

        logging.info(
            f"Completed background recommendation generation for company {company_vat_number}"
        )
    except Exception as e:
        logging.error(f"Error in background recommendation generation: {e}")


@companies_router.patch("/company/", response_model=CompanySchema)
async def update_current_company(
    company_update: CompanyUpdateSchema, auth_user: AuthUser = Depends(get_auth_user)
) -> CompanySchema:
    """Update the authenticated user's company with partial data."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        # Get the user's company to verify ownership
        existing_company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not existing_company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Get only the fields that were actually provided in the update request
        update_data = company_update.model_dump(exclude_unset=True, exclude_none=True)

        # Add the VAT number for the database query
        update_data["vat_number"] = existing_company.vat_number

        # Ensure the authenticated user's email stays in the emails list if emails are being updated
        if "emails" in update_data and auth_user.email not in update_data["emails"]:
            update_data["emails"].append(auth_user.email)

        # Update in database with only the changed fields
        updated_company = crud_company.update_company(
            company_schema=update_data, session=session
        )

        if not updated_company:
            raise HTTPException(status_code=500, detail="Failed to update company")
        
        return await convert_company_to_schema(updated_company)


@companies_router.post("/company/scrape-website", response_model=dict)
async def scrape_company_website_endpoint(
    request: WebsiteScrapingRequest,
    auth_user: AuthUser = Depends(get_auth_user),
) -> dict:
    """
    Scrape a company website to automatically extract company information.
    This can be used during onboarding to pre-fill company details.
    """
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    # Get the OpenAI client
    client = get_openai_client()

    # Scrape the website
    try:
        scraped_data_str = await scrape_company_website(
            website_url=str(request.website_url), client=client
        )

        if not scraped_data_str:
            raise HTTPException(
                status_code=422,
                detail="Could not extract information from the provided website",
            )

        # Parse the JSON response
        try:
            scraped_data = json.loads(scraped_data_str)
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON response: {scraped_data_str}")
            raise HTTPException(
                status_code=500, detail="Error processing website information"
            )

        # Process sectors to match our schema format
        processed_sectors = []
        if scraped_data.get("sectors"):
            for sector_data in scraped_data["sectors"]:
                if sector_data.get("sector") and sector_data.get("confidence", 0) > 0.5:
                    processed_sectors.append(
                        {
                            "sector": sector_data["sector"],
                            "cpv_codes": sector_data["cpv_codes"],
                        }
                    )

        # Construct response with fields suitable for onboarding
        response = {
            "vat_number": re.sub(r'[^a-zA-Z0-9]', '', scraped_data.get("vat_number")),
            "name": scraped_data.get("company_name"),
            "summary_activities": scraped_data.get("summary_activities"),
            "interested_sectors": processed_sectors,
            "employee_count": scraped_data.get("employee_count"),
            "operating_regions": scraped_data.get("operating_regions", []),
            "activity_keywords": scraped_data.get("activity_keywords", []),
        }

        return response

    except Exception as e:
        logging.error(f"Error in website scraping: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error processing website: {str(e)}"
        )
