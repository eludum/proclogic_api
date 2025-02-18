

from fastapi import Depends, APIRouter

from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

import app.crud.company as crud_company
from app.config.postgres import get_session_generator
from app.crud.mapper import convert_company_to_schema
from app.schemas.publication_schemas import CompanySchema

companies_router = APIRouter()


@companies_router.post("/company/")
async def create_company(company: CompanySchema) -> CompanySchema:
    return crud_company.create_company(company=company)


@companies_router.patch("/company/{vat_number}")
async def update_company(company: CompanySchema) -> CompanySchema:
    return crud_company.update_company(company=company)


@companies_router.delete("/company/{vat_number}")
async def delete_company(vat_number: str) -> JSONResponse:
    return crud_company.delete_company(vat_number=vat_number)


@companies_router.get("/company/{email}", response_model=CompanySchema)
async def get_company_by_email(
    email: str, session: Session = Depends(get_session_generator)
) -> CompanySchema:
    company = crud_company.get_company_by_email(email=email, session=session)
    company = convert_company_to_schema(company) if company else None
    return (
        company
        if company
        else JSONResponse(status_code=404, content={"message": "Company not found"})
    )