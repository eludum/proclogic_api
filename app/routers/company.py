from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import JSONResponse

import app.crud.company as crud_company
from app.config.postgres import get_session
from app.crud.mapper import convert_company_to_schema
from app.schemas.company_schemas import CompanySchema
from app.util.clerk import AuthUser, get_auth_user

companies_router = APIRouter()


@companies_router.get("/company/", response_model=CompanySchema)
async def get_current_company(auth_user: AuthUser = Depends(get_auth_user)) -> CompanySchema:
    """Get the company for the authenticated user by email."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")
        
    with get_session() as session:
        company = crud_company.get_company_by_email(email=auth_user.email, session=session)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
            
        # Directly return the company schema instead of the coroutine
        return await convert_company_to_schema(company)


@companies_router.get("/company/{vat_number}", response_model=CompanySchema)
async def get_company_by_vat_number(
    vat_number: str,
    auth_user: AuthUser = Depends(get_auth_user)
) -> CompanySchema:
    """Get a company by its VAT number. User must be authenticated."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")
        
    with get_session() as session:
        # Check if the user has access to this company (admin check or same company)
        user_company = crud_company.get_company_by_email(email=auth_user.email, session=session)
        if not user_company or user_company.vat_number != vat_number:
            raise HTTPException(status_code=403, detail="Not authorized to access this company")
            
        company = crud_company.get_company_by_vat_number(vat_number=vat_number, session=session)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
            
        # Directly return the company schema
        return await convert_company_to_schema(company)


# TODO: update recommended publications when adding company
@companies_router.post("/company/", response_model=CompanySchema)
async def create_company(
    company: CompanySchema,
    auth_user: AuthUser = Depends(get_auth_user)
) -> CompanySchema:
    """Create a new company. User must be authenticated."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")
        
    # Ensure the company email includes the authenticated user's email
    if auth_user.email not in company.emails:
        company.emails.append(auth_user.email)
        
    with get_session() as session:
        # Check if the user already has a company
        existing_company = crud_company.get_company_by_email(email=auth_user.email, session=session)
        if existing_company:
            raise HTTPException(status_code=400, detail="User already has a company")
            
        created_company = crud_company.create_company(company=company, session=session)
        if not created_company:
            raise HTTPException(status_code=500, detail="Failed to create company")
            
        return created_company


# TODO: update recommended publications when updating company
@companies_router.patch("/company/", response_model=CompanySchema)
async def update_current_company(
    company: CompanySchema,
    auth_user: AuthUser = Depends(get_auth_user)
) -> CompanySchema:
    """Update the authenticated user's company."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")
        
    with get_session() as session:
        # Get the user's company to verify ownership
        existing_company = crud_company.get_company_by_email(email=auth_user.email, session=session)
        if not existing_company:
            raise HTTPException(status_code=404, detail="Company not found")
            
        # Ensure VAT number can't be changed
        if company.vat_number != existing_company.vat_number:
            raise HTTPException(status_code=400, detail="Cannot change company VAT number")
            
        # Ensure the authenticated user's email stays in the emails list
        if auth_user.email not in company.emails:
            company.emails.append(auth_user.email)
            
        updated_company = crud_company.update_company(company=company, session=session)
        if not updated_company:
            raise HTTPException(status_code=500, detail="Failed to update company")
            
        return updated_company


# TODO: update recommended publications when deleting company
@companies_router.delete("/company/", status_code=200)
async def delete_current_company(auth_user: AuthUser = Depends(get_auth_user)) -> JSONResponse:
    """Delete the authenticated user's company."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")
        
    with get_session() as session:
        # Get the user's company to verify ownership
        existing_company = crud_company.get_company_by_email(email=auth_user.email, session=session)
        if not existing_company:
            raise HTTPException(status_code=404, detail="Company not found")
            
        success = crud_company.delete_company(vat_number=existing_company.vat_number, session=session)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete company")
            
        return JSONResponse(content={"message": "Company deleted successfully"})