from sqlalchemy.exc import IntegrityError
from models.publication_models import CPVCode, Lot, Publication, Description
from schemas.publication_schemas import PublicationSchema
from config.postgres import get_session


async def create_publication(
    publication_data: PublicationSchema
) -> PublicationSchema:
    """
    Create a new publication in the database.

    Args:
        publication_data (PublicationSchema): The data for creating the publication.
        db (AsyncSession): The database session.

    Returns:
        PublicationSchema: The newly created publication as a Pydantic schema.
    """

    async with get_session() as session:

        try:
            # Handle the main CPV code and descriptions
            cpv_additional_codes = [
                CPVCode(
                    code=cpvcode.code,
                    descriptions=[
                        Description(language=desc.language, text=desc.text)
                        for desc in cpvcode.descriptions
                    ],
                )
                for cpvcode in publication_data.cpvAdditionalCodes
            ]

            # Handle lots and associated descriptions
            lots = [
                Lot(
                    reserved_execution=lot.reservedExecution,
                    reserved_participation=lot.reservedParticipation,
                    descriptions=[
                        Description(language=desc.language, text=desc.text)
                        for desc in lot.descriptions
                    ],
                    titles=[
                        Description(language=desc.language, text=desc.text)
                        for desc in lot.titles
                    ],
                )
                for lot in publication_data.lots
            ]


            new_publication = Publication(
                publication_workspace_id=publication_data.publicationWorkspaceId,
                dispatch_date=publication_data.dispatchDate,
                insertion_date=publication_data.insertionDate,
                natures=publication_data.natures,
                notice_ids=publication_data.noticeIds,
                notice_sub_type=publication_data.noticeSubType,
                nuts_codes=publication_data.nutsCodes,
                procedure_id=publication_data.procedureId,
                publication_date=publication_data.publicationDate,
                publication_languages=publication_data.publicationLanguages,
                publication_reference_numbers_bda=publication_data.publicationReferenceNumbersBDA,
                publication_reference_numbers_ted=publication_data.publicationReferenceNumbersTED,
                publication_type=publication_data.publicationType,
                published_at=publication_data.publishedAt,
                reference_number=publication_data.referenceNumber,
                sent_at=publication_data.sentAt,
                ted_published=publication_data.tedPublished,
                vault_submission_deadline=publication_data.vaultSubmissionDeadline,
                ai_summary=publication_data.ai_summary,
                cpv_additional_codes=cpv_additional_codes,
                cpv_main_code_id=publication_data.cpvMainCode.code,
                cpv_main_code=publication_data.cpvMainCode,
                dossier_id=publication_data.dossier.referenceNumber,
                dossier=publication_data.dossier,
                organisation_id=publication_data.organisation.organisationId,
                organisation=publication_data.organisation,
                lots=lots,
                recommended=publication_data.recommended or [],
            )
            
            session.add(new_publication)
            await session.commit()

            return PublicationSchema.model_validate(new_publication)

        except IntegrityError as e:
            await session.rollback()
            raise ValueError(f"Error creating publication: {str(e)}")
