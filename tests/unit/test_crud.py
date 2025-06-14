import pytest
from datetime import datetime

from app.crud.company import (
    create_company,
    get_company_by_vat,
    get_company_by_email,
    update_company,
    get_all_companies,
)
from app.crud.publication import (
    get_publication_by_workspace_id,
    search_publications,
    get_publications_paginated,
)
from app.schemas.company_schemas import CompanySchema, SectorSchema
from tests.fixtures.test_data import create_test_company, create_test_publication


class TestCompanyCRUD:
    def test_create_company_crud(self, db_session):
        """Test creating a company through CRUD."""
        company_schema = CompanySchema(
            vat_number="BE9876543210",
            name="New Test Company",
            emails=["info@newcompany.com"],
            subscription="team",
            number_of_employees=100,
            summary_activities="Software development",
            interested_sectors=[
                SectorSchema(sector="IT Services", cpv_codes=["72000000"])
            ],
        )

        company = create_company(company_schema, db_session)

        assert company.vat_number == "BE9876543210"
        assert company.name == "New Test Company"
        assert len(company.interested_sectors) == 1

    def test_get_company_by_vat(self, db_session):
        """Test retrieving company by VAT number."""
        company = create_test_company(db_session)

        found_company = get_company_by_vat(company.vat_number, db_session)

        assert found_company is not None
        assert found_company.vat_number == company.vat_number

    def test_get_company_by_email(self, db_session):
        """Test retrieving company by email."""
        company = create_test_company(db_session)

        found_company = get_company_by_email("test@company.com", db_session)

        assert found_company is not None
        assert found_company.vat_number == company.vat_number

    def test_update_company(self, db_session):
        """Test updating company information."""
        company = create_test_company(db_session)

        updated = update_company(
            vat_number=company.vat_number,
            number_of_employees=75,
            summary_activities="Updated activities",
            session=db_session,
        )

        assert updated.number_of_employees == 75
        assert updated.summary_activities == "Updated activities"


class TestPublicationCRUD:
    def test_get_publication_by_workspace_id(self, db_session):
        """Test retrieving publication by workspace ID."""
        publication = create_test_publication(db_session)

        found = get_publication_by_workspace_id(
            publication.publication_workspace_id, db_session
        )

        assert found is not None
        assert found.publication_workspace_id == publication.publication_workspace_id

    def test_search_publications(self, db_session):
        """Test searching publications."""
        # Create test publications
        pub1 = create_test_publication(
            db_session,
            publication_workspace_id="2024-S-001-111111",
            extracted_keywords=["highway", "construction"],
        )
        pub2 = create_test_publication(
            db_session,
            publication_workspace_id="2024-S-002-222222",
            extracted_keywords=["software", "development"],
        )

        # Search for construction
        results, total = search_publications(
            search_query="construction", limit=10, offset=0, session=db_session
        )

        assert total >= 1
        assert any(
            p.publication_workspace_id == pub1.publication_workspace_id for p in results
        )

    def test_publications_pagination(self, db_session):
        """Test pagination of publications."""
        # Create multiple publications
        for i in range(5):
            create_test_publication(
                db_session, publication_workspace_id=f"2024-S-00{i}-{i}00000"
            )

        results, total = get_publications_paginated(session=db_session, page=1, size=2)

        assert len(results) == 2
        assert total == 5
