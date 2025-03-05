from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql import exists
import logging

from app.models.publication_models import (
    CPVCode,
    Description,
    Dossier,
    EnterpriseCategory,
    Lot,
    Organisation,
    OrganisationName,
    Publication,
    CompanyPublicationMatch,
)
from app.schemas.publication_schemas import (
    CPVCodeSchema,
    CompanyPublicationMatchSchema,
    DescriptionSchema,
    DossierSchema,
    EnterpriseCategorySchema,
    LotSchema,
    OrganisationNameSchema,
    OrganisationSchema,
    PublicationSchema,
)


def get_or_create_descriptions(
    descriptions_schema: List[DescriptionSchema], session: Session
) -> List[Description]:
    description_instances = []
    for desc_schema in descriptions_schema:
        # Calculate the MD5 hash of the text
        text_hash = func.md5(desc_schema.text)

        # Check if a description with the same text and language already exists
        description = (
            session.query(Description)
            .filter(
                Description.language == desc_schema.language,
                func.md5(Description.text) == text_hash,
            )
            .first()
        )

        if not description:
            description = Description(
                language=desc_schema.language, text=desc_schema.text
            )
            session.add(description)
            session.flush()

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
            session.flush()

        organisation_name_instances.append(org_name)

    return organisation_name_instances


def get_or_create_organisation(
    organisation_schema: OrganisationSchema, session: Session
) -> Organisation:
    organisation = session.get(Organisation, organisation_schema.organisation_id)

    if not organisation:
        organisation = Organisation(
            organisation_id=organisation_schema.organisation_id,
            tree=organisation_schema.tree,
        )

        session.add(organisation)
        session.flush()

        organisation.organisation_names = get_or_create_organisation_names(
            organisation_names_schema=organisation_schema.organisation_names,
            organisation_id=organisation.organisation_id,
            session=session,
        )

        session.add(organisation)
        session.flush()

    return organisation


def create_enterprise_categories(
    enterprise_categories_schema: List[EnterpriseCategorySchema],
    dossier_reference_number: str,
    session: Session,
) -> List[EnterpriseCategory]:
    enterprise_categories_instances = []
    for entc_schema in enterprise_categories_schema:
        entc = EnterpriseCategory(
            category_code=entc_schema.category_code,
            levels=entc_schema.levels,
            dossier_reference_number=dossier_reference_number,
        )
        session.add(entc)
        session.flush()
        enterprise_categories_instances.append(entc)
    return enterprise_categories_instances


def get_or_create_dossier(dossier_schema: DossierSchema, session: Session) -> Dossier:
    dossier = session.get(Dossier, dossier_schema.reference_number)
    if not dossier:
        dossier = Dossier(
            reference_number=dossier_schema.reference_number,
            accreditations=dossier_schema.accreditations,
            legal_basis=dossier_schema.legal_basis,
            number=dossier_schema.number,
            procurement_procedure_type=dossier_schema.procurement_procedure_type,
            special_purchasing_technique=dossier_schema.special_purchasing_technique,
            descriptions=get_or_create_descriptions(
                descriptions_schema=dossier_schema.descriptions, session=session
            ),
            titles=get_or_create_descriptions(
                descriptions_schema=dossier_schema.titles, session=session
            ),
        )
        session.add(dossier)
        session.flush()
        
        dossier.enterprise_categories = create_enterprise_categories(
            dossier_schema.enterprise_categories, dossier_schema.reference_number, session
        )
        session.flush()

    return dossier


def create_lot(lot_schema: LotSchema, session: Session) -> Lot:
    lot = Lot(
        reserved_execution=lot_schema.reserved_execution,
        reserved_participation=lot_schema.reserved_participation,
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

    cpv_main_code = get_or_create_cpv_code(
        cpv_code_schema=publication_schema.cpv_main_code, session=session
    )
    dossier = get_or_create_dossier(
        dossier_schema=publication_schema.dossier, session=session
    )
    organisation = get_or_create_organisation(
        organisation_schema=publication_schema.organisation, session=session
    )

    cpv_additional_codes = []
    for cpv_code in publication_schema.cpv_additional_codes:
        cpv_additional_codes.append(
            get_or_create_cpv_code(
                cpv_code_schema=cpv_code,
                session=session,
            )
        )

    lots = []
    for lot in publication_schema.lots:
        lots.append(create_lot(lot_schema=lot, session=session))

    publication.dispatch_date = publication_schema.dispatch_date
    publication.insertion_date = publication_schema.insertion_date
    publication.natures = publication_schema.natures
    publication.notice_ids = publication_schema.notice_ids
    publication.notice_sub_type = publication_schema.notice_sub_type
    publication.nuts_codes = publication_schema.nuts_codes
    publication.procedure_id = publication_schema.procedure_id
    publication.publication_date = publication_schema.publication_date
    publication.publication_languages = publication_schema.publication_languages
    publication.publication_reference_numbers_bda = (
        publication_schema.publication_reference_numbers_bda
    )
    publication.publication_reference_numbers_ted = (
        publication_schema.publication_reference_numbers_ted
    )
    publication.publication_type = publication_schema.publication_type
    publication.published_at = publication_schema.published_at
    publication.reference_number = publication_schema.reference_number
    publication.sent_at = publication_schema.sent_at
    publication.ted_published = publication_schema.ted_published
    publication.vault_submission_deadline = publication_schema.vault_submission_deadline
    if publication_schema.ai_summary_without_documents:
        publication.ai_summary_without_documents = publication_schema.ai_summary_without_documents
    if publication_schema.ai_summary_with_documents:
        publication.ai_summary_with_documents = publication_schema.ai_summary_with_documents
    if publication_schema.estimated_value:
        publication.estimated_value = publication_schema.estimated_value
    if publication_schema.extracted_keywords:
        publication.extracted_keywords = publication_schema.extracted_keywords
    if publication_schema.award:
        publication.award = publication_schema.award

    publication.cpv_main_code = cpv_main_code
    publication.dossier = dossier
    publication.organisation = organisation
    publication.cpv_additional_codes = cpv_additional_codes
    publication.lots = lots

    if publication_schema.company_matches:
        # Get existing matches to update them
        existing_matches = {
            match.company_vat_number: match 
            for match in session.query(CompanyPublicationMatch).filter(
                CompanyPublicationMatch.publication_workspace_id == publication.publication_workspace_id
            ).all()
        }
        
        # Create or update matches
        for match_schema in publication_schema.company_matches:
            if match_schema.company_vat_number in existing_matches:
                match = existing_matches[match_schema.company_vat_number]
                # Update existing match
                match.match_percentage = match_schema.match_percentage
                match.is_recommended = match_schema.is_recommended
                match.is_saved = match_schema.is_saved
                match.is_viewed = match_schema.is_viewed
            else:
                # Create new match
                new_match = CompanyPublicationMatch(
                    company_vat_number=match_schema.company_vat_number,
                    publication_workspace_id=publication.publication_workspace_id,
                    match_percentage=match_schema.match_percentage,
                    is_recommended=match_schema.is_recommended,
                    is_saved=match_schema.is_saved,
                    is_viewed=match_schema.is_viewed
                )
                session.add(new_match)

    session.add(publication)
    session.flush()

    return publication


def get_or_create_publication(
    publication_schema: PublicationSchema, session: Session
) -> Publication:
    publication = session.get(Publication, publication_schema.publication_workspace_id)

    if publication:
        update_publication(
            publication=publication,
            publication_schema=publication_schema,
            session=session,
        )
    else:
        cpv_main_code = get_or_create_cpv_code(
            cpv_code_schema=publication_schema.cpv_main_code, session=session
        )
        dossier = get_or_create_dossier(
            dossier_schema=publication_schema.dossier, session=session
        )
        organisation = get_or_create_organisation(
            organisation_schema=publication_schema.organisation, session=session
        )

        cpv_additional_codes = []
        for cpv_code in publication_schema.cpv_additional_codes:
            cpv_additional_codes.append(
                get_or_create_cpv_code(
                    cpv_code_schema=cpv_code,
                    session=session,
                )
            )

        lots = []
        for lot in publication_schema.lots:
            lots.append(create_lot(lot_schema=lot, session=session))

        # Create new publication with updated fields
        publication = Publication(
            publication_workspace_id=publication_schema.publication_workspace_id,
            dispatch_date=publication_schema.dispatch_date,
            insertion_date=publication_schema.insertion_date,
            natures=publication_schema.natures,
            notice_ids=publication_schema.notice_ids,
            notice_sub_type=publication_schema.notice_sub_type,
            nuts_codes=publication_schema.nuts_codes,
            procedure_id=publication_schema.procedure_id,
            publication_date=publication_schema.publication_date,
            publication_languages=publication_schema.publication_languages,
            publication_reference_numbers_bda=publication_schema.publication_reference_numbers_bda,
            publication_reference_numbers_ted=publication_schema.publication_reference_numbers_ted,
            publication_type=publication_schema.publication_type,
            published_at=publication_schema.published_at,
            reference_number=publication_schema.reference_number,
            sent_at=publication_schema.sent_at,
            ted_published=publication_schema.ted_published,
            vault_submission_deadline=publication_schema.vault_submission_deadline,
            ai_summary_without_documents=publication_schema.ai_summary_without_documents,
            ai_summary_with_documents=publication_schema.ai_summary_with_documents,
            estimated_value=publication_schema.estimated_value,
            extracted_keywords=publication_schema.extracted_keywords,
            award=publication_schema.award,
            cpv_main_code=cpv_main_code,
            dossier=dossier,
            organisation=organisation,
            cpv_additional_codes=cpv_additional_codes,
            lots=lots,
        )

        session.add(publication)
        session.flush()
        
        # Create company matches if they exist in the schema
        if publication_schema.company_matches:
            for match_schema in publication_schema.company_matches:
                company_match = CompanyPublicationMatch(
                    company_vat_number=match_schema.company_vat_number,
                    publication_workspace_id=publication.publication_workspace_id,
                    match_percentage=match_schema.match_percentage,
                    is_recommended=match_schema.is_recommended,
                    is_saved=match_schema.is_saved,
                    is_viewed=match_schema.is_viewed
                )
                session.add(company_match)
            session.flush()

    try:
        session.commit()
        return publication
    except Exception as e:
        logging.error("Error creating publication: %s", e)
        session.rollback()
        raise
    finally:
        session.close()


def get_publication_by_workspace_id(
    publication_workspace_id: str, session: Session
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
            joinedload(Publication.company_matches),
        )
        .first()
    )


def publication_exists(publication_workspace_id: str, session: Session) -> bool:
    """Check if a publication already exists."""
    return session.query(
        exists().where(Publication.publication_workspace_id == publication_workspace_id)
    ).scalar()


def delete_publication(publication_workspace_id: str, session: Session):
    """Delete a publication and its related data."""
    try:
        # First delete the company-publication matches
        session.query(CompanyPublicationMatch).filter(
            CompanyPublicationMatch.publication_workspace_id == publication_workspace_id
        ).delete(synchronize_session=False)
        
        # Then delete the publication
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
        raise


def get_all_publications(session: Session) -> List[Publication]:
    """Retrieve all publications."""
    return (
        session.query(Publication)
        # filter added here to only see active ones
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
            joinedload(Publication.company_matches),
        )
        .all()
    )


def search_publications(search_term: str, session: Session) -> List[Publication]:
    """Search publications by lots titles, dossier titles, lots descriptions, dossier descriptions, and organisation names."""
    search_pattern = f"%{search_term}%"

    description_subquery = (
        session.query(Description.id)
        .filter(func.lower(Description.text).like(func.lower(search_pattern)))
        .subquery()
    )

    organisation_name_subquery = (
        session.query(OrganisationName.id)
        .filter(func.lower(OrganisationName.text).like(func.lower(search_pattern)))
        .subquery()
    )

    dossier_title_subquery = (
        session.query(Description.id)
        .filter(func.lower(Description.text).like(func.lower(search_pattern)))
        .correlate(Dossier)
        .subquery()
    )

    lot_title_subquery = (
        session.query(Description.id)
        .filter(func.lower(Description.text).like(func.lower(search_pattern)))
        .correlate(Lot)
        .subquery()
    )

    # Add search in extracted_keywords
    publications_with_keywords = (
        session.query(Publication)
        .filter(
            Publication.extracted_keywords.isnot(None),
            func.array_to_string(Publication.extracted_keywords, ',', '').ilike(search_pattern)
        )
    )

    return (
        session.query(Publication)
        .join(Publication.dossier)
        .join(Publication.organisation)
        .join(Publication.lots)
        .filter(
            Publication.dossier.has(
                Dossier.descriptions.any(Description.id.in_(description_subquery))
            )
            | Publication.organisation.has(
                Organisation.organisation_names.any(
                    OrganisationName.id.in_(organisation_name_subquery)
                )
            )
            | Publication.dossier.has(
                Dossier.titles.any(Description.id.in_(dossier_title_subquery))
            )
            | Publication.lots.any(
                Lot.descriptions.any(Description.id.in_(lot_title_subquery))
            )
            | Publication.publication_workspace_id.in_(
                publications_with_keywords.with_entities(Publication.publication_workspace_id)
            )
        )
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
            joinedload(Publication.company_matches),
        )
        .all()
    )