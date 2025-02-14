import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from app.config.postgres import get_session
from app.models.publication_models import (
    CPVCode,
    Description,
    Dossier,
    EnterpriseCategory,
    Lot,
    Organisation,
    OrganisationName,
    Publication,
)
from app.schemas.publication_schemas import (
    CPVCodeSchema,
    DescriptionSchema,
    DossierSchema,
    EnterpriseCategorySchema,
    LotSchema,
    OrganisationSchema,
    OrganisationNameSchema,
    PublicationSchema,
)
from sqlalchemy.orm import joinedload


def get_or_create_descriptions(
    descriptions_schema: List[DescriptionSchema], session: Session
) -> List[Description]:
    description_instances = []
    for desc_schema in descriptions_schema:
        description = (
            session.query(Description)
            .filter_by(language=desc_schema.language, text=desc_schema.text)
            .first()
        )
        if not description:
            description = Description(
                language=desc_schema.language, text=desc_schema.text
            )
            session.add(description)
        description_instances.append(description)
    return description_instances


def get_or_create_cpv_code(cpv_code_schema: CPVCodeSchema, session: Session) -> CPVCode:
    cpv_code = session.get(CPVCode, cpv_code_schema.code)
    if not cpv_code:
        cpv_code = CPVCode(
            code=cpv_code_schema.code,
            descriptions=get_or_create_descriptions(
                descriptions_schema=cpv_code_schema.descriptions, session=session
            ),
        )
        session.add(cpv_code)
        session.flush()

    return cpv_code


def get_or_create_organisation_names(
    organisation_names_schema: List[OrganisationNameSchema],
    organisation_id: int,
    session: Session,
) -> List[OrganisationName]:
    organisation_name_instances = []
    for org_name_schema in organisation_names_schema:
        org_name = (
            session.query(OrganisationName)
            .filter_by(
                language=org_name_schema.language,
                text=org_name_schema.text,
                organisation_id=organisation_id,
            )
            .first()
        )
        if not org_name:
            org_name = OrganisationName(
                language=org_name_schema.language,
                text=org_name_schema.text,
                organisation_id=organisation_id,
            )
            session.add(org_name)
        organisation_name_instances.append(org_name)

    return organisation_name_instances


def get_or_create_organisation(
    organisation_schema: OrganisationSchema, session: Session
) -> Organisation:
    organisation = session.get(Organisation, organisation_schema.organisationId)

    if not organisation:
        organisation = Organisation(
            organisation_id=organisation_schema.organisationId,
            tree=organisation_schema.tree,
        )

        session.add(organisation)
        session.flush()

        organisation.organisation_names = get_or_create_organisation_names(
            organisation_names_schema=organisation_schema.organisationNames,
            organisation_id=organisation.organisation_id,
            session=session,
        )

        session.add(organisation)
        session.flush()

    return organisation


def create_enterprise_categories(
    enterprise_categories_schema: List[EnterpriseCategorySchema],
    dossier_reference_number: str,
) -> List[EnterpriseCategory]:
    enterprise_categories_instances = []
    for entc_schema in enterprise_categories_schema:
        entc = EnterpriseCategory(
            category_code=entc_schema.categoryCode,
            levels=entc_schema.levels,
            dossier_reference_number=dossier_reference_number,
        )
        enterprise_categories_instances.append(entc)
    return enterprise_categories_instances


def get_or_create_dossier(dossier_schema: DossierSchema, session: Session) -> Dossier:
    dossier = session.get(Dossier, dossier_schema.referenceNumber)
    if not dossier:
        dossier = Dossier(
            reference_number=dossier_schema.referenceNumber,
            accreditations=dossier_schema.accreditations,
            legal_basis=dossier_schema.legalBasis,
            number=dossier_schema.number,
            procurement_procedure_type=dossier_schema.procurementProcedureType,
            special_purchasing_technique=dossier_schema.specialPurchasingTechnique,
            descriptions=get_or_create_descriptions(
                descriptions_schema=dossier_schema.descriptions, session=session
            ),
            titles=get_or_create_descriptions(
                descriptions_schema=dossier_schema.titles, session=session
            ),
            enterprise_categories=create_enterprise_categories(
                dossier_schema.enterpriseCategories, dossier_schema.referenceNumber
            ),
        )
        session.add(dossier)
        session.flush()

    return dossier


def create_lot(lot_schema: LotSchema, session: Session) -> Lot:
    lot = Lot(
        reserved_execution=lot_schema.reservedExecution,
        reserved_participation=lot_schema.reservedParticipation,
        descriptions=get_or_create_descriptions(
            descriptions_schema=lot_schema.descriptions, session=session
        ),
        titles=get_or_create_descriptions(
            descriptions_schema=lot_schema.titles, session=session
        ),
    )

    session.add(lot)
    session.flush()

    return lot


def update_publication(
    publication: Publication,
    publication_schema: PublicationSchema,
    session: Session,
) -> Publication:
    publication.dispatch_date = publication_schema.dispatchDate
    publication.insertion_date = publication_schema.insertionDate
    publication.natures = publication_schema.natures
    publication.notice_ids = publication_schema.noticeIds
    publication.notice_sub_type = publication_schema.noticeSubType
    publication.nuts_codes = publication_schema.nutsCodes
    publication.procedure_id = publication_schema.procedureId
    publication.publication_date = publication_schema.publicationDate
    publication.publication_languages = publication_schema.publicationLanguages
    publication.publication_reference_numbers_bda = (
        publication_schema.publicationReferenceNumbersBDA
    )
    publication.publication_reference_numbers_ted = (
        publication_schema.publicationReferenceNumbersTED
    )
    publication.publication_type = publication_schema.publicationType
    publication.published_at = publication_schema.publishedAt
    publication.reference_number = publication_schema.referenceNumber
    publication.sent_at = publication_schema.sentAt
    publication.ted_published = publication_schema.tedPublished
    publication.vault_submission_deadline = publication_schema.vaultSubmissionDeadline
    publication.ai_summary = publication_schema.ai_summary

    publication.cpv_main_code = get_or_create_cpv_code(
        cpv_code_schema=publication_schema.cpvMainCode, session=session
    )
    publication.dossier = get_or_create_dossier(
        dossier_schema=publication_schema.dossier,
        session=session,
    )
    publication.organisation = get_or_create_organisation(
        organisation_schema=publication_schema.organisation,
        session=session,
    )

    cpv_additional_codes = []
    for cpv_code in publication_schema.cpvAdditionalCodes:
        cpv_additional_codes.append(
            get_or_create_cpv_code(cpv_code_schema=cpv_code, session=session)
        )
    publication.cpv_additional_codes = cpv_additional_codes

    lots = []
    for lot in publication_schema.lots:
        lots.append(create_lot(lot_schema=lot, session=session))
    publication.lots = lots

    session.add(publication)
    session.flush()

    return publication


def get_or_create_publication(
    publication_schema: PublicationSchema,
    session: Session = get_session(),
) -> Publication:
    publication = session.get(Publication, publication_schema.publicationWorkspaceId)
    if publication:
        update_publication(
            publication=publication,
            publication_schema=publication_schema,
            session=session,
        )
    if not publication:
        cpv_additional_codes = []
        for cpv_code in publication_schema.cpvAdditionalCodes:
            cpv_additional_codes.append(
                get_or_create_cpv_code(
                    cpv_code_schema=cpv_code,
                    session=session,
                )
            )

        lots = []
        for lot in publication_schema.lots:
            lots.append(create_lot(lot_schema=lot, session=session))

        publication = Publication(
            publication_workspace_id=publication_schema.publicationWorkspaceId,
            dispatch_date=publication_schema.dispatchDate,
            insertion_date=publication_schema.insertionDate,
            natures=publication_schema.natures,
            notice_ids=publication_schema.noticeIds,
            notice_sub_type=publication_schema.noticeSubType,
            nuts_codes=publication_schema.nutsCodes,
            procedure_id=publication_schema.procedureId,
            publication_date=publication_schema.publicationDate,
            publication_languages=publication_schema.publicationLanguages,
            publication_reference_numbers_bda=publication_schema.publicationReferenceNumbersBDA,
            publication_reference_numbers_ted=publication_schema.publicationReferenceNumbersTED,
            publication_type=publication_schema.publicationType,
            published_at=publication_schema.publishedAt,
            reference_number=publication_schema.referenceNumber,
            sent_at=publication_schema.sentAt,
            ted_published=publication_schema.tedPublished,
            vault_submission_deadline=publication_schema.vaultSubmissionDeadline,
            ai_summary=publication_schema.ai_summary,
            cpv_main_code=get_or_create_cpv_code(
                cpv_code_schema=publication_schema.cpvMainCode, session=session
            ),
            dossier=get_or_create_dossier(
                dossier_schema=publication_schema.dossier, session=session
            ),
            organisation=get_or_create_organisation(
                organisation_schema=publication_schema.organisation, session=session
            ),
            cpv_additional_codes=cpv_additional_codes,
            lots=lots,
        )
        session.add(publication)
        session.flush()
    try:
        session.commit()
        return publication
    except Exception as e:
        logging.error("Error creating publication: %s", e)
        session.rollback()
    finally:
        session.close()


def get_publication_by_workspace_id(
    publication_workspace_id: str, session: Session = get_session()
) -> Optional[Publication]:
    """Retrieve Publication by its workspace ID with all related data."""
    return (
        session.query(Publication)
        .filter(Publication.publication_workspace_id == publication_workspace_id)
        .options(
            joinedload(Publication.cpv_main_code),
            joinedload(Publication.dossier).joinedload(Dossier.descriptions),
            joinedload(Publication.dossier).joinedload(Dossier.titles),
            joinedload(Publication.dossier).joinedload(Dossier.enterprise_categories),
            joinedload(Publication.organisation).joinedload(
                Organisation.organisation_names
            ),
            joinedload(Publication.cpv_additional_codes),
            joinedload(Publication.lots).joinedload(Lot.descriptions),
            joinedload(Publication.lots).joinedload(Lot.titles),
            joinedload(Publication.recommended_companies),
        )
        .first()
    )


def delete_publication(publication_workspace_id: str, session: Session = get_session()):
    """Delete a publication and its related data."""
    try:
        publication = (
            session.query(Publication)
            .filter_by(publication_workspace_id=publication_workspace_id)
            .first()
        )
        if publication:
            session.delete(publication)
            session.commit()
            logging.info(
                f"Publication with workspace ID {publication_workspace_id} deleted successfully."
            )
        else:
            logging.warning(
                f"Publication with workspace ID {publication_workspace_id} not found."
            )
    except Exception as e:
        logging.error("Error deleting publication: %s", e)
        session.rollback()


def get_all_publications(session: Session = get_session()) -> List[Publication]:
    """Retrieve all publications related to a given VAT number."""
    return (
        session.query(Publication)
        .filter(Publication.vault_submission_deadline.isnot(None))
        .options(
            joinedload(Publication.cpv_main_code),
            joinedload(Publication.dossier).joinedload(Dossier.descriptions),
            joinedload(Publication.dossier).joinedload(Dossier.titles),
            joinedload(Publication.dossier).joinedload(Dossier.enterprise_categories),
            joinedload(Publication.organisation).joinedload(
                Organisation.organisation_names
            ),
            joinedload(Publication.cpv_additional_codes),
            joinedload(Publication.lots).joinedload(Lot.descriptions),
            joinedload(Publication.lots).joinedload(Lot.titles),
            joinedload(Publication.recommended_companies),
        )
        .all()
    )
