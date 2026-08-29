import logging
from datetime import datetime, date, timedelta
from typing import List, Optional, Tuple

from app.models.publication_contract_models import (
    Contract,
    ContractAddress,
    ContractContactPerson,
    ContractOrganization,
)
from app.models.publication_models import (
    CompanyPublicationMatch,
    CPVCode,
    Description,
    KIND_DESCRIPTION,
    KIND_TITLE,
    KIND_UNKNOWN,
    Dossier,
    EnterpriseCategory,
    Lot,
    Organisation,
    OrganisationName,
    Publication,
)
from app.schemas.publication_contract_schemas import (
    ContractAddressSchema,
    ContractContactPersonSchema,
    ContractOrganizationSchema,
    ContractSchema,
)
from app.schemas.publication_schemas import (
    CPVCodeSchema,
    DescriptionSchema,
    DossierSchema,
    EnterpriseCategorySchema,
    LotSchema,
    OrganisationNameSchema,
    OrganisationSchema,
    PublicationSchema,
)
from app.crud.fts import build_fts_condition, build_fts_rank
from app.util.publication_utils.searchable import refresh_searchable_content
from sqlalchemy import and_, case, desc, func, literal_column, or_, select
from sqlalchemy.orm import Session, aliased, joinedload, selectinload, subqueryload
from sqlalchemy.sql import exists


def create_descriptions(
    descriptions_schema: List[DescriptionSchema],
    session: Session,
    kind: str = KIND_UNKNOWN,
) -> List[Description]:
    """Create one Description row per incoming text, tagged with its kind.

    This deliberately does NOT reuse an existing row with the same text. It used
    to: it looked up any description with matching text and language, anywhere in
    the database, and handed that row to the new parent. But a description row
    carries a single dossier_reference_number and a single lot_id, so "reusing"
    one actually *moved* it -- reassigning the foreign key and silently stripping
    the text from whichever dossier or lot had it before.

    That was not hypothetical. update_publication rebuilds a publication's lots
    on every notice update, and two tenders sharing a phrase as ordinary as
    "Onderhoud groenzones" is routine, so republished notices quietly emptied
    each other's lots.

    Rows are cheap; correctness here is not.
    """
    description_instances = []
    for desc_schema in descriptions_schema:
        description = Description(
            language=desc_schema.language, text=desc_schema.text, kind=kind
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
            descriptions=create_descriptions(
                descriptions_schema=cpv_code_schema.descriptions,
                session=session,
                kind=KIND_DESCRIPTION,
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
        existing_org_name = (
            session.query(OrganisationName)
            .filter_by(
                language=org_name_schema.language,
                text=org_name_schema.text,
            )
            .first()
        )

        if existing_org_name:
            if existing_org_name.organisation_id != organisation_id:
                existing_org_name.organisation_id = organisation_id
                session.add(existing_org_name)

            organisation_name_instances.append(existing_org_name)
        else:
            # Create new if it doesn't exist at all
            new_org_name = OrganisationName(
                language=org_name_schema.language,
                text=org_name_schema.text,
                organisation_id=organisation_id,
            )
            session.add(new_org_name)
            session.flush()
            organisation_name_instances.append(new_org_name)

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
            descriptions=create_descriptions(
                descriptions_schema=dossier_schema.descriptions,
                session=session,
                kind=KIND_DESCRIPTION,
            ),
            titles=create_descriptions(
                descriptions_schema=dossier_schema.titles,
                session=session,
                kind=KIND_TITLE,
            ),
        )
        session.add(dossier)
        session.flush()

        dossier.enterprise_categories = create_enterprise_categories(
            dossier_schema.enterprise_categories,
            dossier_schema.reference_number,
            session,
        )
        session.flush()

    return dossier


def create_lot(lot_schema: LotSchema, session: Session) -> Lot:
    lot = Lot(
        reserved_execution=lot_schema.reserved_execution or [],
        reserved_participation=lot_schema.reserved_participation or [],
        descriptions=create_descriptions(
            descriptions_schema=lot_schema.descriptions,
            session=session,
            kind=KIND_DESCRIPTION,
        ),
        titles=create_descriptions(
            descriptions_schema=lot_schema.titles,
            session=session,
            kind=KIND_TITLE,
        ),
    )

    session.add(lot)
    session.flush()

    return lot


def create_contract_address(
    address_schema: ContractAddressSchema, session: Session
) -> ContractAddress:
    address = ContractAddress(
        street=address_schema.street[:255] if address_schema.street else None,
        city=address_schema.city[:100] if address_schema.city else None,
        postal_code=address_schema.postal_code[:20] if address_schema.postal_code else None,
        country=address_schema.country[:100] if address_schema.country else None,
        nuts_code=address_schema.nuts_code[:10] if address_schema.nuts_code else None,
    )
    session.add(address)
    session.flush()
    return address


def create_contract_contact_person(
    person_schema: ContractContactPersonSchema,
    session: Session,
) -> ContractContactPerson:
    person = ContractContactPerson(
        name=person_schema.name[:255] if person_schema.name else None,
        job_title=person_schema.job_title[:255] if person_schema.job_title else None,
        phone=person_schema.phone[:50] if person_schema.phone else None,
        email=person_schema.email[:255] if person_schema.email else None,
    )

    session.add(person)
    session.flush()
    return person


def get_or_create_contract_organization(
    org_schema: ContractOrganizationSchema, session: Session
) -> ContractOrganization:
    organization = (
        session.query(ContractOrganization)
        .filter(ContractOrganization.business_id == org_schema.business_id)
        .first()
    )

    address = None
    if org_schema.address is not None:
        address = create_contract_address(org_schema.address, session=session)

    contact_persons = []
    for person_schema in org_schema.contact_persons:
        contact_persons.append(
            create_contract_contact_person(person_schema, session=session)
        )

    if not organization:
        organization = ContractOrganization(
            name=org_schema.name[:255] if org_schema.name else None,
            business_id=org_schema.business_id[:50] if org_schema.business_id else None,
            website=org_schema.website[:255] if org_schema.website else None,
            phone=org_schema.phone[:50] if org_schema.phone else None,
            email=org_schema.email[:255] if org_schema.email else None,
            company_size=org_schema.company_size[:50] if org_schema.company_size else None,
            subcontracting=org_schema.subcontracting[:100] if org_schema.subcontracting else None,
            address=address,
            contact_persons=contact_persons,
        )

        session.add(organization)
        session.flush()

    return organization


def get_or_create_contract(
    contract_schema: ContractSchema, session: Session
) -> Contract:
    contract = session.get(Contract, contract_schema.contract_id)

    contracting_authority = None
    if contract_schema.contracting_authority is not None:
        contracting_authority = get_or_create_contract_organization(
            contract_schema.contracting_authority, session
        )

    winning_publisher = None
    if contract_schema.winning_publisher is not None:
        winning_publisher = get_or_create_contract_organization(
            contract_schema.winning_publisher, session
        )

    appeals_body = None
    if contract_schema.appeals_body is not None:
        appeals_body = get_or_create_contract_organization(
            contract_schema.appeals_body, session
        )

    service_provider = None
    if contract_schema.service_provider is not None:
        service_provider = get_or_create_contract_organization(
            contract_schema.service_provider, session
        )

    if not contract:
        contract = Contract(
            notice_id=contract_schema.notice_id,
            contract_id=contract_schema.contract_id,
            internal_id=contract_schema.internal_id,
            issue_date=contract_schema.issue_date,
            notice_type=contract_schema.notice_type,
            total_contract_amount=contract_schema.total_contract_amount,
            currency=contract_schema.currency,
            lowest_publication_amount=contract_schema.lowest_publication_amount,
            highest_publication_amount=contract_schema.highest_publication_amount,
            number_of_publications_received=contract_schema.number_of_publications_received,
            number_of_participation_requests=contract_schema.number_of_participation_requests,
            electronic_auction_used=contract_schema.electronic_auction_used,
            dynamic_purchasing_system=contract_schema.dynamic_purchasing_system,
            framework_agreement=contract_schema.framework_agreement[:50] if contract_schema.framework_agreement else None,
            contracting_authority=contracting_authority,
            winning_publisher=winning_publisher,
            appeals_body=appeals_body,
            service_provider=service_provider,
        )

        session.add(contract)
        session.flush()

    return contract


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
        publication.ai_summary_without_documents = (
            publication_schema.ai_summary_without_documents
        )
    if publication_schema.ai_summary_with_documents:
        publication.ai_summary_with_documents = (
            publication_schema.ai_summary_with_documents
        )
    if publication_schema.estimated_value:
        publication.estimated_value = publication_schema.estimated_value
    if publication_schema.extracted_keywords:
        publication.extracted_keywords = publication_schema.extracted_keywords
    if publication_schema.contract:
        publication.contract = publication_schema.contract

    publication.cpv_main_code = cpv_main_code
    publication.dossier = dossier
    publication.organisation = organisation
    publication.cpv_additional_codes = cpv_additional_codes
    publication.lots = lots

    if publication_schema.company_matches:
        # Get existing matches to update them
        existing_matches = {
            match.company_vat_number: match
            for match in session.query(CompanyPublicationMatch)
            .filter(
                CompanyPublicationMatch.publication_workspace_id
                == publication.publication_workspace_id
            )
            .all()
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
                    is_viewed=match_schema.is_viewed,
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

        contract = None
        if publication_schema.contract:
            contract = get_or_create_contract(publication_schema.contract, session)

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
            contract=contract,
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
                    is_viewed=match_schema.is_viewed,
                )
                session.add(company_match)
            session.flush()

    # Flatten the tender's text onto the row so it is searchable. Done here
    # rather than in the caller because this is the one place both the create
    # and the update path pass through.
    refresh_searchable_content(publication, session)

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
    """Retrieve Publication by its workspace ID with all related data, safely closing the session."""
    try:
        publication = (
            session.query(Publication)
            .filter(Publication.publication_workspace_id == publication_workspace_id)
            .options(
                # Use joinedload for direct relationships
                joinedload(Publication.cpv_main_code),
                joinedload(Publication.dossier).subqueryload(Dossier.descriptions),
                joinedload(Publication.dossier).subqueryload(Dossier.titles),
                joinedload(Publication.dossier).subqueryload(
                    Dossier.enterprise_categories
                ),
                joinedload(Publication.organisation).subqueryload(
                    Organisation.organisation_names
                ),
                # Use subqueryload for collections to avoid cartesian products
                subqueryload(Publication.cpv_additional_codes),
                subqueryload(Publication.lots).subqueryload(Lot.descriptions),
                subqueryload(Publication.lots).subqueryload(Lot.titles),
                subqueryload(Publication.company_matches),
                # Load contract and its organizations separately
                joinedload(Publication.contract),
            )
            .first()
        )

        # Load contract organizations in separate queries to avoid timeout
        if publication and publication.contract:
            if publication.contract.contracting_authority:
                _ = publication.contract.contracting_authority.address
                _ = publication.contract.contracting_authority.contact_persons
            if publication.contract.winning_publisher:
                _ = publication.contract.winning_publisher.address
                _ = publication.contract.winning_publisher.contact_persons
            if publication.contract.appeals_body:
                _ = publication.contract.appeals_body.address
                _ = publication.contract.appeals_body.contact_persons
            if publication.contract.service_provider:
                _ = publication.contract.service_provider.address
                _ = publication.contract.service_provider.contact_persons

        return publication
    except Exception as e:
        logging.error("Error retrieving publication: %s", e)
        return None
    finally:
        session.close()


def publication_exists(publication_workspace_id: str, session: Session) -> bool:
    """Check if a publication already exists."""
    return session.query(
        exists().where(Publication.publication_workspace_id == publication_workspace_id)
    ).scalar()


def build_region_filter_conditions(region_filter: List[str]):
    """
    Build SQLAlchemy filter conditions for region filtering.
    Handles both exact matches and hierarchical NUTS code relationships.

    NUTS codes have a hierarchical structure:
    - BE: Belgium (country level)
    - BE1, BE2, BE3: Major regions
    - BE21, BE22, etc.: Provinces
    - BE211, BE212, etc.: Arrondissements

    A publication matches if:
    1. It has an exact match with a requested region
    2. It has a child region of a requested region (e.g., BE21 matches BE211)
    3. It has a parent region of a requested region (e.g., BE211 matches BE21)
    """
    if not region_filter:
        return None

    conditions = []

    for requested_region in region_filter:
        # Condition 1: Exact match
        exact_match = Publication.nuts_codes.any(requested_region)

        # Condition 2: Publication has child regions of requested region
        # If we're looking for BE21, we want to match BE211, BE212, etc.
        child_pattern = f"{requested_region}%"
        child_match = (
            select(literal_column("1"))
            .select_from(func.unnest(Publication.nuts_codes).alias("code"))
            .where(literal_column("code").like(child_pattern))
            .correlate(Publication)
            .exists()
        )

        # Condition 3: Publication has parent regions of requested region
        # If we're looking for BE211, we want to match BE21, BE2, BE
        parent_conditions = []
        for i in range(1, len(requested_region)):
            parent_region = requested_region[:i]
            parent_conditions.append(Publication.nuts_codes.any(parent_region))

        # Combine all conditions for this region
        region_conditions = [exact_match, child_match]
        if parent_conditions:
            region_conditions.extend(parent_conditions)

        conditions.append(or_(*region_conditions))

    # Return OR of all region conditions
    return or_(*conditions) if conditions else None


def get_paginated_publications_for_company(
    session: Session,
    company_vat_number: str,
    page: int = 1,
    size: int = 10,
    recommended: Optional[bool] = None,
    saved: Optional[bool] = None,
    viewed: Optional[bool] = None,
    active: bool = True,
    search_term: Optional[str] = None,
    region_filter: Optional[List[str]] = None,
    sector_filter: Optional[List[str]] = None,
    cpv_code_filter: Optional[List[str]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sort_by: Optional[str] = None,
    sort_order: str = "desc",
) -> Tuple[List[Publication], int]:
    """
    Get publications for a specific company with pagination and filtering at the database level.
    Returns both the publications for the current page and the total count.
    """
    # Start with a query that joins the company matches
    Match = aliased(CompanyPublicationMatch)

    # Base query with initial join to CompanyPublicationMatch (left outer join)
    query = session.query(Publication, Match).outerjoin(
        Match,
        and_(
            Match.publication_workspace_id == Publication.publication_workspace_id,
            Match.company_vat_number == company_vat_number,
        ),
    )

    # Apply active filter
    if active:
        # Use vault_submission_deadline to determine active status
        query = query.filter(
            Publication.vault_submission_deadline.isnot(None),
            Publication.vault_submission_deadline > func.now(),
        )

    # Apply company-specific filters
    if recommended is not None:
        if recommended:
            # Must have a match with is_recommended=True
            query = query.filter(
                Match.company_vat_number == company_vat_number,
                Match.is_recommended == True,
            )
        else:
            # Either no match or is_recommended=False
            query = query.filter(
                or_(
                    Match.company_vat_number.is_(None),
                    and_(
                        Match.company_vat_number == company_vat_number,
                        Match.is_recommended == False,
                    ),
                )
            )

    if saved is not None:
        if saved:
            # Must have a match with is_saved=True
            query = query.filter(
                Match.company_vat_number == company_vat_number, Match.is_saved == True
            )
        else:
            # Either no match or is_saved=False
            query = query.filter(
                or_(
                    Match.company_vat_number.is_(None),
                    and_(
                        Match.company_vat_number == company_vat_number,
                        Match.is_saved == False,
                    ),
                )
            )

    if viewed is not None:
        if viewed:
            # Must have a match with is_viewed=True
            query = query.filter(
                Match.company_vat_number == company_vat_number, Match.is_viewed == True
            )
        else:
            # Either no match or is_viewed=False
            query = query.filter(
                or_(
                    Match.company_vat_number.is_(None),
                    and_(
                        Match.company_vat_number == company_vat_number,
                        Match.is_viewed == False,
                    ),
                )
            )

    # Apply search term filter
    # Match against the flattened text blob rather than joining out to
    # descriptions and organisation_names. build_searchable_content() already
    # folds in every field the old correlated subqueries reached -- dossier and
    # lot titles and descriptions, organisation names, extracted keywords -- so
    # this is a superset of what they matched, and it is index-backed:
    # lower(descriptions.text) LIKE '%term%' over ~388k rows could not use an
    # index and cost ~8s a query.
    if search_term and search_term.strip():
        fts_condition = build_fts_condition(search_term)
        if fts_condition is not None:
            query = query.filter(fts_condition)

    # Apply region filter at database level
    if region_filter and len(region_filter) > 0:
        region_conditions = build_region_filter_conditions(region_filter)
        if region_conditions is not None:
            query = query.filter(region_conditions)

    # Apply sector filter
    if sector_filter and len(sector_filter) > 0:
        sector_conditions = []
        for sector_code in sector_filter:
            # For sector filtering, we use the first two digits which define the sector category
            # For example, "45000000" should match all codes starting with "45"
            if len(sector_code) >= 2:
                sector_prefix = sector_code[:2]
                sector_conditions.append(
                    Publication.cpv_main_code_code.startswith(sector_prefix)
                )

        if sector_conditions:
            query = query.filter(or_(*sector_conditions))

    # Apply CPV code filter (for exact code matches)
    if cpv_code_filter and len(cpv_code_filter) > 0:
        # Use exact matches for CPV code filter, not just sector matches
        cpv_conditions = [Publication.cpv_main_code_code.in_(cpv_code_filter)]

        if cpv_conditions:
            query = query.filter(or_(*cpv_conditions))

    # Apply date range filters
    if date_from:
        query = query.filter(func.date(Publication.publication_date) >= date_from)

    if date_to:
        query = query.filter(func.date(Publication.publication_date) <= date_to)

    # Get total count before pagination
    count_query = query.with_entities(func.count())
    total_count = count_query.scalar()

    # Relevance leads whenever there is a search term; the requested sort then
    # breaks ties. order_by() appends, so calling it here and letting the block
    # below add its own keys yields "rank first, then the caller's choice".
    # Without this, matching any term and ordering purely by date buries the
    # best match behind whatever happens to be newest.
    fts_rank = build_fts_rank(search_term)
    if fts_rank is not None:
        query = query.order_by(fts_rank.desc())

    # Apply sorting
    # Create a case expression for match percentage to handle NULL values
    match_percentage = case(
        (Match.match_percentage.is_(None), 0), else_=Match.match_percentage
    ).label("match_percentage")

    # Add sorting logic
    if sort_by:
        if sort_by == "match_percentage":
            if sort_order.lower() == "desc":
                query = query.order_by(desc(match_percentage))
            else:
                query = query.order_by(match_percentage)
        elif sort_by == "publication_date":
            if sort_order.lower() == "desc":
                query = query.order_by(desc(Publication.publication_date))
            else:
                query = query.order_by(Publication.publication_date)
        elif sort_by == "deadline":
            # For deadline, sort NULLs last
            if sort_order.lower() == "desc":
                query = query.order_by(
                    Publication.vault_submission_deadline.is_(None),
                    desc(Publication.vault_submission_deadline),
                )
            else:
                query = query.order_by(
                    Publication.vault_submission_deadline.is_(None),
                    Publication.vault_submission_deadline,
                )
    else:
        # Apply automatic sorting based on filters
        if recommended is not None and recommended:
            query = query.order_by(
                desc(match_percentage), desc(Publication.publication_date)
            )
        elif saved is not None and saved:
            # For saved publications, sort by updated_at
            query = query.order_by(Match.updated_at.is_(None), desc(Match.updated_at))
        elif viewed is not None and viewed:
            # For viewed publications, sort by updated_at
            query = query.order_by(Match.updated_at.is_(None), desc(Match.updated_at))
        else:
            # Default sort by publication date
            query = query.order_by(desc(Publication.publication_date))

    # Apply pagination and eager loading.
    # selectinload (not joinedload) for the *collection* relationships: chaining
    # joinedload across several one-to-many collections builds a cartesian
    # product (descriptions x titles x lots x company_matches x ...), which blew
    # this query up to ~12s on the live table and tripped the gateway timeout
    # (502). selectinload emits one extra SELECT per relationship instead —
    # ~0.5s here. joinedload is kept only for the scalar cpv_main_code.
    query = (
        query.options(
            joinedload(Publication.cpv_main_code),
            selectinload(Publication.dossier).selectinload(Dossier.descriptions),
            selectinload(Publication.dossier).selectinload(Dossier.titles),
            selectinload(Publication.dossier).selectinload(
                Dossier.enterprise_categories
            ),
            selectinload(Publication.organisation).selectinload(
                Organisation.organisation_names
            ),
            selectinload(Publication.cpv_additional_codes),
            selectinload(Publication.lots).selectinload(Lot.descriptions),
            selectinload(Publication.lots).selectinload(Lot.titles),
            selectinload(Publication.company_matches),
        )
        .offset((page - 1) * size)
        .limit(size)
    )

    # Execute the query and process the results
    results = query.all()

    # Extract publications and enrich them with match data
    publications = []
    for pub, match in results:
        if match:
            # Add match metadata to publication
            pub.match_percentage = match.match_percentage
            pub.saved_at = match.updated_at if match.is_saved else None
            pub.viewed_at = match.updated_at if match.is_viewed else None
        else:
            pub.match_percentage = 0
            pub.saved_at = None
            pub.viewed_at = None

        publications.append(pub)

    return publications, total_count


def get_paginated_publications_free(
    session: Session,
    page: int = 1,
    size: int = 10,
    search_term: Optional[str] = None,
    sort_by: str = "publication_date",
    sort_order: str = "desc",
    region_filter: Optional[List[str]] = None,
    sector_filter: Optional[List[str]] = None,
) -> Tuple[List[Publication], int]:
    """
    Retrieve publications with pagination, sorting, and filtering applied at the database level.
    Handles both regular listing and search in a single function.
    Returns both the publications for the current page and the total count.
    """
    # Base query with required joins
    query = session.query(Publication).filter(
        Publication.vault_submission_deadline.isnot(None)
    )

    # Apply search term if provided
    # Match against the flattened text blob rather than joining out to
    # descriptions and organisation_names. build_searchable_content() already
    # folds in every field the old correlated subqueries reached -- dossier and
    # lot titles and descriptions, organisation names, extracted keywords -- so
    # this is a superset of what they matched, and it is index-backed:
    # lower(descriptions.text) LIKE '%term%' over ~388k rows could not use an
    # index and cost ~8s a query.
    if search_term and search_term.strip():
        fts_condition = build_fts_condition(search_term)
        if fts_condition is not None:
            query = query.filter(fts_condition)

    # Apply region filter at database level
    if region_filter and len(region_filter) > 0:
        region_conditions = build_region_filter_conditions(region_filter)
        if region_conditions is not None:
            query = query.filter(region_conditions)

    # Apply sector filter
    if sector_filter and len(sector_filter) > 0:
        sector_conditions = []
        for sector_code in sector_filter:
            # For sector filtering, we use the first two digits which define the sector category
            if len(sector_code) >= 2:
                sector_prefix = sector_code[:2]
                sector_conditions.append(
                    Publication.cpv_main_code_code.startswith(sector_prefix)
                )

        if sector_conditions:
            query = query.filter(or_(*sector_conditions))

    # Get total count before pagination
    total_count = query.count()

    # Relevance leads whenever there is a search term; the requested sort then
    # breaks ties. order_by() appends, so calling it here and letting the block
    # below add its own keys yields "rank first, then the caller's choice".
    # Without this, matching any term and ordering purely by date buries the
    # best match behind whatever happens to be newest.
    fts_rank = build_fts_rank(search_term)
    if fts_rank is not None:
        query = query.order_by(fts_rank.desc())

    # Apply sorting
    if sort_by == "publication_date":
        if sort_order.lower() == "desc":
            query = query.order_by(desc(Publication.publication_date))
        else:
            query = query.order_by(Publication.publication_date)
    # Add other sorting options as needed

    # Apply pagination and eager loading.
    # selectinload (not joinedload) for the *collection* relationships: chaining
    # joinedload across several one-to-many collections builds a cartesian
    # product (descriptions x titles x lots x company_matches x ...), which blew
    # this query up to ~12s on the live table and tripped the gateway timeout
    # (502). selectinload emits one extra SELECT per relationship instead —
    # ~0.5s here. joinedload is kept only for the scalar cpv_main_code.
    publications = (
        query.options(
            joinedload(Publication.cpv_main_code),
            selectinload(Publication.dossier).selectinload(Dossier.descriptions),
            selectinload(Publication.dossier).selectinload(Dossier.titles),
            selectinload(Publication.dossier).selectinload(
                Dossier.enterprise_categories
            ),
            selectinload(Publication.organisation).selectinload(
                Organisation.organisation_names
            ),
            selectinload(Publication.cpv_additional_codes),
            selectinload(Publication.lots).selectinload(Lot.descriptions),
            selectinload(Publication.lots).selectinload(Lot.titles),
            selectinload(Publication.company_matches),
        )
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    return publications, total_count


def get_publications_with_upcoming_deadlines(
    session: Session, days_ahead: int = 7
) -> List[Tuple[Publication, str, int]]:
    """
    Get publications with deadlines in the next X days that users have saved.
    Returns tuples of (publication, company_vat_number, days_left).
    """
    try:
        now = datetime.now()
        future_date = now + timedelta(days=days_ahead)

        results = (
            session.query(Publication, CompanyPublicationMatch.company_vat_number)
            .join(CompanyPublicationMatch)
            .filter(
                Publication.vault_submission_deadline.isnot(
                    None
                ),  # Ensure deadline exists
                Publication.vault_submission_deadline >= now,  # Not in the past
                Publication.vault_submission_deadline
                <= future_date,  # Within time window
                CompanyPublicationMatch.is_saved == True,
            )
            .all()
        )

        # Calculate days left for each
        deadlines_with_days = []
        for publication, company_vat_number in results:
            # Calculate days left more accurately
            time_diff = publication.vault_submission_deadline - now
            days_left = max(0, time_diff.days)  # Ensure non-negative

            if time_diff.total_seconds() > 0 and days_left == 0:
                days_left = 0

            deadlines_with_days.append((publication, company_vat_number, days_left))

        return deadlines_with_days

    except Exception as e:
        logging.error(f"Error getting publications with upcoming deadlines: {e}")
        return []
