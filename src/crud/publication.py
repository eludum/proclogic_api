import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from config.postgres import get_session
from models.publication_models import (CPVCode, Description, Dossier,
                                       EnterpriseCategory, Lot, Organisation,
                                       OrganisationName, Publication)
from schemas.publication_schemas import PublicationSchema


def get_or_create_descriptions(descriptions: List[Description]) -> List[Description]:
    description_instances = []
    for desc_schema in descriptions:
        description_instance = Description(
            language=desc_schema.language,
            text=desc_schema.text,
        )
        description_instances.append(description_instance)
    return description_instances


def get_or_create_cpv_code(session: Session, cpv_code_data: CPVCode) -> CPVCode:
    cpv_code = session.get(CPVCode, cpv_code_data.code)
    if not cpv_code:
        cpv_code = CPVCode(
            code=cpv_code_data.code,
            descriptions=get_or_create_descriptions(
                descriptions=cpv_code_data.descriptions
            ),
        )
        session.add(cpv_code)
        session.flush()

    return cpv_code


def get_or_create_organisation_names(
    session: Session, organisation_names: List[OrganisationName], organisation_id: int
) -> List[OrganisationName]:
    organisation_names = []
    for org_name_schema in organisation_names:
        org_name = (
            session.query(OrganisationName)
            .filter_by(language=org_name_schema.language, text=org_name_schema.text)
            .first()
        )
        if not org_name:
            org_name = OrganisationName(
                language=org_name_schema.language,
                text=org_name_schema.text,
                organisation_id=organisation_id,
            )
        organisation_names.append(org_name)

    return organisation_names


def get_or_create_organisation(
    session: Session, organisation_data: Organisation
) -> Organisation:
    organisation = session.get(Organisation, organisation_data.organisationId)

    if not organisation:
        organisation = Organisation(
            organisation_id=organisation_data.organisationId,
            tree=organisation_data.tree,
        )

        session.add(organisation)
        session.flush()

        organisation.organisation_names = get_or_create_organisation_names(
            session=session,
            organisation_names=organisation_data.organisationNames,
            organisation_id=organisation.organisation_id,
        )

        session.add(organisation)
        session.flush()

    return organisation


def get_or_create_enterprise_categories(
    enterprise_categories: List[str], dossier_reference_number: str
) -> List[EnterpriseCategory]:
    enterprise_categories_instances = []
    for entc_schema in enterprise_categories:
        entc = EnterpriseCategory(
            category_code=entc_schema.categoryCode,
            levels=entc_schema.levels,
            dossier_reference_number=dossier_reference_number,
        )
        enterprise_categories_instances.append(entc)
    return enterprise_categories_instances


def get_or_create_dossier(session: Session, dossier_data: Dossier) -> Dossier:
    dossier = session.get(Dossier, dossier_data.referenceNumber)
    if not dossier:
        dossier = Dossier(
            reference_number=dossier_data.referenceNumber,
            accreditations=dossier_data.accreditations,
            legal_basis=dossier_data.legalBasis,
            number=dossier_data.number,
            procurement_procedure_type=dossier_data.procurementProcedureType,
            special_purchasing_technique=dossier_data.specialPurchasingTechnique,
            descriptions=get_or_create_descriptions(
                descriptions=dossier_data.descriptions
            ),
            titles=get_or_create_descriptions(descriptions=dossier_data.titles),
            enterprise_categories=get_or_create_enterprise_categories(
                dossier_data.enterpriseCategories, dossier_data.referenceNumber
            ),
        )
        session.add(dossier)
        session.flush()

    return dossier


def create_lot(session: Session, lot_data: Lot) -> Lot:
    lot = Lot(
        reserved_execution=lot_data.reservedExecution,
        reserved_participation=lot_data.reservedParticipation,
        descriptions=get_or_create_descriptions(descriptions=lot_data.descriptions),
        titles=get_or_create_descriptions(descriptions=lot_data.titles),
    )

    session.add(lot)
    session.flush()

    return lot


def get_or_create_publication(
    publication_data: PublicationSchema,
    session: Session = get_session(),
) -> Publication:
    # TODO: Check if the publication already exists
    cpv_additional_codes = []
    for cpv_code_data in publication_data.cpvAdditionalCodes:
        cpv_additional_codes.append(
            get_or_create_cpv_code(
                session=session,
                cpv_code_data=cpv_code_data,
            )
        )

    lots = []
    for lot_data in publication_data.lots:
        lots.append(create_lot(session=session, lot_data=lot_data))

    publication = Publication(
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
        cpv_main_code=get_or_create_cpv_code(
            session=session, cpv_code_data=publication_data.cpvMainCode
        ),
        dossier=get_or_create_dossier(
            session=session, dossier_data=publication_data.dossier
        ),
        organisation=get_or_create_organisation(
            session=session, organisation_data=publication_data.organisation
        ),
        cpv_additional_codes=cpv_additional_codes,
        lots=lots,
    )
    session.add(publication)
    session.flush()

    session.commit()

    return publication


def create_or_update_publication(
    publication_data: PublicationSchema, session: Session = get_session()
):
    """Create or update a Publication instance."""
    try:
        publication = get_or_create_publication(
            publication_data=publication_data, session=session
        )
        session.commit()
        logging.info(
            f"Publication with workspace ID {publication.publication_workspace_id} created or updated successfully."
        )
    except Exception as e:
        logging.error("Error creating or updating publication: %s", e)
        session.rollback()


def get_publication_by_workspace_id(
    publication_workspace_id: str, session: Session = get_session()
) -> Optional[Publication]:
    """Retrieve Publication by its workspace ID."""
    return (
        session.query(Publication)
        .filter(Publication.publication_workspace_id == publication_workspace_id)
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
