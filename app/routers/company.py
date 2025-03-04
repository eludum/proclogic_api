from fastapi import APIRouter
from starlette.responses import JSONResponse

import app.crud.company as crud_company
from app.config.postgres import get_session
from app.crud.mapper import convert_company_to_schema
from app.schemas.company_schemas import CompanySchema

companies_router = APIRouter()


@companies_router.get("/company/{email}", response_model=CompanySchema)
async def get_company_by_email(email: str) -> CompanySchema:
    with get_session() as session:
        company = crud_company.get_company_by_email(email=email, session=session)
        company = convert_company_to_schema(company) if company else None
        return (
            company
            if company
            else JSONResponse(status_code=404, content={"message": "Company not found"})
        )


# TODO: update recommended publications when adding company
@companies_router.post("/company/", response_model=CompanySchema)
async def create_company(company: CompanySchema) -> CompanySchema:
    with get_session() as session:
        return crud_company.create_company(company=company, session=session)


# TODO: update recommended publications when updating company
@companies_router.patch("/company/{vat_number}", response_model=CompanySchema)
async def update_company(company: CompanySchema) -> CompanySchema:
    with get_session() as session:
        return crud_company.update_company(company=company, session=session)


# TODO: update recommended publications when deleting company
@companies_router.delete("/company/{vat_number}")
async def delete_company(vat_number: str) -> JSONResponse:
    with get_session() as session:
        return crud_company.delete_company(vat_number=vat_number, session=session)
