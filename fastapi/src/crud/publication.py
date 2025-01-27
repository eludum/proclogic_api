import logging
from typing import List

from sqlalchemy.orm import Session

from config.postgres import get_session
from models.publication_models import (CPVCode, Description, Dossier,
                                       EnterpriseCategory, Lot, Organisation,
                                       OrganisationName, Publication)
from schemas.publication_schemas import PublicationSchema


def check_if_descriptions_exist(
    session: Session, descriptions: List[Description]
) -> List[Description]:
    descriptions = []
    for desc in descriptions:
        # Check if the description already exists in the database
        existing_desc = session.query(Description).filter_by(text=desc.text).first()
        if existing_desc:
            description_instance = existing_desc
        else:
            description_instance = Description(
                language=desc.language,
                text=desc.text,
            )
        descriptions.append(description_instance)

    return descriptions


def check_if_publications_exist(session: Session, publication: Publication) -> Publication:
    existing_publication = session.query(Publication).filter_by(
        publication_workspace_id=publication.publication_workspace_id
    ).first()
    if existing_publication:
        return existing_publication


def create_publication(publication_data: PublicationSchema):

    # TODO: implement rollback, split into smaller parts, add logging, create or update flows
    #       check for each one if it already exists or not
    session = get_session()
    try:            
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
        )
        session.add(publication)
        session.flush()  # Ensure `publication` is written and has an ID
        # Add the main CPV code
        cpv_main_code = CPVCode(
            code=publication_data.cpvMainCode.code,
            descriptions=check_if_descriptions_exist(
                session=session, descriptions=publication_data.cpvMainCode.descriptions
            ),
            publication_workspace_id=publication_data.publicationWorkspaceId,
        )
        cpv_in_db = session.get(CPVCode, publication_data.cpvMainCode.code)
        if not cpv_in_db:
            session.add(cpv_main_code)
            session.flush()
            publication.cpv_main_code = cpv_main_code  # Assign the new instance
        else:
            publication.cpv_main_code = cpv_in_db  # Assign the existing instance

        # Add related CPV codes
        for cpvcode in publication_data.cpvAdditionalCodes:
            cpv_code_instance = CPVCode(
                code=cpvcode.code,
                descriptions=check_if_descriptions_exist(
                    session=session, descriptions=cpvcode.descriptions
                ),
                publication_workspace_id=publication_data.publicationWorkspaceId,
            )
            cpv_in_db = session.get(CPVCode, cpvcode.code)
            if not cpv_in_db:
                session.add(cpv_code_instance)
                session.flush()
                publication.cpv_additional_codes.append(
                    cpv_code_instance
                )  # Append the new instance
            else:
                publication.cpv_additional_codes.append(
                    cpv_in_db
                )  # Append the existing instance

        # Add other related objects (dossier, organisation, lots, etc.)
        dossier = Dossier(
            reference_number=publication_data.dossier.referenceNumber,
            accreditations=publication_data.dossier.accreditations,
            legal_basis=publication_data.dossier.legalBasis,
            number=publication_data.dossier.number,
            procurement_procedure_type=publication_data.dossier.procurementProcedureType,
            special_purchasing_technique=publication_data.dossier.specialPurchasingTechnique,
            descriptions=check_if_descriptions_exist(
                session=session, descriptions=publication_data.dossier.descriptions
            ),
            titles=check_if_descriptions_exist(
                session=session, descriptions=publication_data.dossier.titles
            ),
            publication_workspace_id=publication_data.publicationWorkspaceId,
        )
        session.add(dossier)
        session.flush()
        enterprise_categories = [
            EnterpriseCategory(
                category_code=entc.categoryCode,
                levels=entc.levels,
                dossier_reference_number=publication_data.dossier.referenceNumber,
            )
            for entc in publication_data.dossier.enterpriseCategories
        ]
        session.add_all(enterprise_categories)
        session.flush()
        publication.dossier = dossier

        organisation = Organisation(
            organisation_id=publication_data.organisation.organisationId,
            tree=publication_data.organisation.tree,
            organisation_names=[
                OrganisationName(
                    language=org.language,
                    text=org.text,
                    organisation_id=publication_data.organisation.organisationId,
                )
                for org in publication_data.organisation.organisationNames
            ],
            publication_workspace_id=publication_data.publicationWorkspaceId,
        )
        organisation_in_db = session.get(
            Organisation, publication_data.organisation.organisationId
        )
        if not organisation_in_db:
            session.add(organisation)
            session.flush()
            publication.organisation = organisation  # Assign the new instance
        else:
            publication.organisation = organisation_in_db  # Assign the existing instance

        for lot in publication_data.lots:
            lot_instance = Lot(
                reserved_execution=lot.reservedExecution,
                reserved_participation=lot.reservedParticipation,
                descriptions=check_if_descriptions_exist(
                    session=session, descriptions=lot.descriptions
                ),
                titles=check_if_descriptions_exist(
                    session=session, descriptions=lot.titles
                ),
                publication_workspace_id=publication_data.publicationWorkspaceId,
            )
            session.add(lot_instance)
            session.flush()
            publication.lots.append(lot_instance)

        session.add(publication)

        # Commit the transaction to save the publication to the database
        session.commit()
    except Exception as e:
        logging.error(e, "error in creating publication")
        session.rollback()
