from config.postgres import get_db
from models.publication_models import (CPVCode, Description, Dossier,
                                       EnterpriseCategory, Lot, Organisation,
                                       OrganisationName, Publication)
from schemas.publication_schemas import PublicationSchema


def create_publication(publication_data: PublicationSchema):

    session = get_db()

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
        descriptions=[
            Description(
                language=desc.language,
                text=desc.text,
                cpv_code_code=publication_data.cpvMainCode.code,
            )
            for desc in publication_data.cpvMainCode.descriptions
        ],
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
            descriptions=[
                Description(
                    language=desc.language,
                    text=desc.text,
                    cpv_code_code=cpvcode.code,
                )
                for desc in cpvcode.descriptions
            ],
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
        descriptions=[
            Description(
                language=desc.language,
                text=desc.text,
                dossier_reference_number=publication_data.dossier.referenceNumber,
            )
            for desc in publication_data.dossier.descriptions
        ],
        titles=[
            Description(
                language=desc.language,
                text=desc.text,
                dossier_reference_number=publication_data.dossier.referenceNumber,
            )
            for desc in publication_data.dossier.titles
        ],
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
    session.add(organisation)
    session.flush()
    publication.organisation = organisation

    for lot in publication_data.lots:
        lot_instance = Lot(
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
            publication_workspace_id=publication_data.publicationWorkspaceId,
        )
        session.add(lot_instance)
        session.flush()
        publication.lots.append(lot_instance)

    session.add(publication)
