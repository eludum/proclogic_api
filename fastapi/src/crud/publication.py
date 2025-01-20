from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from models.pubproc_models import CPVCode, Lot, Publication, Description
from schemas.pubproc_schemas import PublicationSchema
from config.postgres import get_db_session


async def create_publication(
    publication_data: PublicationSchema, db: AsyncSession = None
) -> PublicationSchema:
    """
    Create a new publication in the database.

    Args:
        publication_data (PublicationSchema): The data for creating the publication.
        db (AsyncSession): The database session.

    Returns:
        PublicationSchema: The newly created publication as a Pydantic schema.
    """
    db = db or await get_db_session()

    async with db:
        try:
            # Handle the main CPV code and descriptions
            cpv_main_code = CPVCode(
                code=publication_data.cpvMainCode.code,
                descriptions=[
                    Description(
                        language=desc.language,
                        text=desc.text
                    ) for desc in publication_data.cpvMainCode.descriptions
                ],
            )
            db.add(cpv_main_code)
            await db.flush()  # Ensures `cpv_main_code` gets an ID

            # Handle lots and associated descriptions
            lots = [
                Lot(
                    reserved_execution=lot.reservedExecution,
                    reserved_participation=lot.reservedParticipation,
                    descriptions=[
                        Description(
                            language=desc.language,
                            text=desc.text
                        ) for desc in lot.descriptions
                    ]
                ) for lot in publication_data.lots
            ]

            # Create the publication
            new_publication = Publication(
                cpv_main_code_id=cpv_main_code.id,
                dispatch_date=publication_data.dispatchDate,
                insertion_date=publication_data.insertionDate,
                notice_sub_type=publication_data.noticeSubType,
                nuts_codes=publication_data.nutsCodes,
                procedure_id=publication_data.procedureId,
                publication_date=publication_data.publicationDate,
                publication_languages=publication_data.publicationLanguages,
                publication_type=publication_data.publicationType,
                publication_workspace_id=publication_data.publicationWorkspaceId,
                published_at=publication_data.publishedAt,
                reference_number=publication_data.referenceNumber,
                sent_at=publication_data.sentAt,
                ted_published=publication_data.tedPublished,
                lots=lots,
                ai_summary=publication_data.ai_summary,
            )

            db.add(new_publication)
            await db.commit()
            await db.refresh(new_publication)

            return PublicationSchema.model_validate(new_publication)

        except IntegrityError as e:
            await db.rollback()
            raise ValueError(f"Error creating publication: {str(e)}")


async def update_publication(
    publication_id: int, publication_data: PublicationSchema, db: AsyncSession = None
) -> PublicationSchema:
    """
    Update an existing publication in the database.

    Args:
        publication_id (int): The ID of the publication to update.
        publication_data (PublicationSchema): The new data for the publication.
        db (AsyncSession): The database session.

    Returns:
        PublicationSchema: The updated publication as a Pydantic schema.
    """
    db = db or await get_db_session()

    async with db:
        result = await db.execute(
            select(Publication).where(Publication.id == publication_id).options(
                joinedload(Publication.cpv_main_code),
                joinedload(Publication.lots)
            )
        )
        publication = result.scalars().first()

        if not publication:
            raise ValueError("Publication not found.")

        # Update CPV main code
        cpv_main_code = publication.cpv_main_code
        cpv_main_code.code = publication_data.cpvMainCode.code
        cpv_main_code.descriptions = [
            Description(language=desc.language, text=desc.text)
            for desc in publication_data.cpvMainCode.descriptions
        ]

        # Update lots and descriptions
        publication.lots = [
            Lot(
                reserved_execution=lot.reservedExecution,
                reserved_participation=lot.reservedParticipation,
                descriptions=[
                    Description(language=desc.language, text=desc.text)
                    for desc in lot.descriptions
                ]
            ) for lot in publication_data.lots
        ]

        # Update publication fields
        publication.dispatch_date = publication_data.dispatchDate
        publication.insertion_date = publication_data.insertionDate
        publication.notice_sub_type = publication_data.noticeSubType
        publication.nuts_codes = publication_data.nutsCodes
        publication.procedure_id = publication_data.procedureId
        publication.publication_date = publication_data.publicationDate
        publication.publication_languages = publication_data.publicationLanguages
        publication.publication_type = publication_data.publicationType
        publication.publication_workspace_id = publication_data.publicationWorkspaceId
        publication.published_at = publication_data.publishedAt
        publication.reference_number = publication_data.referenceNumber
        publication.sent_at = publication_data.sentAt
        publication.ted_published = publication_data.tedPublished
        publication.ai_summary = publication_data.ai_summary

        await db.commit()
        await db.refresh(publication)

        return PublicationSchema.model_validate(publication)


async def delete_publication(publication_id: int, db: AsyncSession = None) -> bool:
    """
    Delete a publication from the database.

    Args:
        publication_id (int): The ID of the publication to delete.
        db (AsyncSession): The database session.

    Returns:
        bool: True if the publication was deleted, False otherwise.
    """
    db = db or await get_db_session()

    async with db:
        result = await db.execute(
            select(Publication).where(Publication.id == publication_id)
        )
        publication = result.scalars().first()

        if not publication:
            raise ValueError("Publication not found.")

        await db.delete(publication)
        await db.commit()
        return True
