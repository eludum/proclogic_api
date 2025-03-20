import logging
import httpx

from app.config.settings import Settings
from app.models.company_models import Company
from app.models.publication_models import Publication
from app.schemas.company_schemas import CompanySchema, SectorSchema
from app.schemas.publication_out_schemas import PublicationOut
from app.schemas.publication_schemas import CompanyPublicationMatchSchema
from app.util.publication_utils.publication_converter import PublicationConverter
from app.util.pubproc import (
    get_publication_workspace_documents,
    get_publication_workspace_forum,
)

settings = Settings()

# TODO: hide stuff for the free part


async def convert_publications_to_out_schema_list_free(
    publication: Publication,
) -> PublicationOut:
    """Convert a publication to the output schema without company-specific data"""
    return PublicationConverter.to_output_schema(publication)


async def convert_publications_to_out_schema_list_paid(
    company: Company, publication: Publication
) -> PublicationOut:
    """Convert a publication to the output schema with company-specific data"""
    return PublicationConverter.to_output_schema(publication, company)


async def convert_publication_to_out_schema_details_free(
    publication: Publication,
) -> PublicationOut:
    """Convert a publication with detailed info to output schema without company-specific data"""
    return PublicationConverter.to_output_schema(publication)


async def convert_publication_to_out_schema_details_paid(
    publication: Publication, company: Company
) -> PublicationOut:
    """Convert a publication with detailed info to output schema with company-specific data"""
    # Get documents and forum info
    async with httpx.AsyncClient() as client:
        documents = await get_publication_workspace_documents(
            client, publication.publication_workspace_id
        )
        forum = await get_publication_workspace_forum(
            client, publication.publication_workspace_id
        )

    # Convert documents to a serializable format
    serializable_documents = {}
    if documents:
        for filename, file_data in documents.items():
            try:
                # Create a metadata object without the actual binary content
                serializable_documents[filename] = {
                    "filename": filename,
                    "size": (
                        len(file_data.read())
                        if hasattr(file_data, "read")
                        else len(file_data.get("content", b""))
                    ),
                    "content_type": getattr(
                        file_data, "content_type", "application/octet-stream"
                    ),
                    # Don't include the actual content in the response
                }

                # Reset file position if it's a file-like object
                if hasattr(file_data, "seek"):
                    file_data.seek(0)
            except Exception as e:
                logging.error(f"Error processing document {filename}: {e}")
                continue

    # Use the converter with all available data
    return PublicationConverter.to_output_schema(
        publication=publication,
        company=company,
        documents=serializable_documents,
        forum=forum,
    )


async def convert_company_to_schema(company: Company) -> CompanySchema:
    """Convert a SQLAlchemy Company model instance to a Pydantic CompanySchema."""
    return CompanySchema(
        vat_number=company.vat_number,
        subscription=company.subscription,
        name=company.name,
        emails=company.emails,
        interested_sectors=[
            SectorSchema(sector=sector.sector, cpv_codes=sector.cpv_codes)
            for sector in company.interested_sectors
        ],
        accreditations=company.accreditations,
        summary_activities=company.summary_activities,
        max_publication_value=company.max_publication_value,
        activity_keywords=company.activity_keywords,
        operating_regions=company.operating_regions,
        publication_matches=[
            CompanyPublicationMatchSchema(
                publication_workspace_id=match.publication_workspace_id,
                company_vat_number=match.company_vat_number,
                is_recommended=match.is_recommended,
                is_saved=match.is_saved,
                is_viewed=match.is_viewed,
                match_percentage=match.match_percentage,
            )
            for match in company.publication_matches
        ],
    )
