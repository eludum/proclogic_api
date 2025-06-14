import pytest
from datetime import datetime, timedelta

from app.models.company_models import Company, Sector
from app.models.publication_models import Publication, CompanyPublicationMatch
from tests.fixtures.test_data import create_test_company, create_test_publication


class TestCompanyModel:
    def test_create_company(self, db_session):
        """Test creating a company."""
        company = create_test_company(db_session)

        assert company.vat_number == "BE0123456789"
        assert company.name == "Test Company NV"
        assert len(company.emails) == 2
        assert company.subscription == "starter"
        assert company.number_of_employees == 50

    def test_company_sectors_relationship(self, db_session):
        """Test company-sectors relationship."""
        company = create_test_company(db_session)

        sector = Sector(
            sector="Construction",
            cpv_codes=["45000000", "45100000"],
            company_vat_number=company.vat_number,
        )
        db_session.add(sector)
        db_session.commit()

        assert len(company.interested_sectors) == 1
        assert company.interested_sectors[0].sector == "Construction"

    def test_company_properties(self, db_session):
        """Test company property methods."""
        company = create_test_company(db_session)
        publication = create_test_publication(db_session)

        # Create a match
        match = CompanyPublicationMatch(
            company_vat_number=company.vat_number,
            publication_workspace_id=publication.publication_workspace_id,
            match_percentage=85.5,
            is_recommended=True,
            is_saved=True,
        )
        db_session.add(match)
        db_session.commit()

        assert len(company.recommended_publications) == 1
        assert len(company.saved_publications) == 1


class TestPublicationModel:
    def test_create_publication(self, db_session):
        """Test creating a publication."""
        publication = create_test_publication(db_session)

        assert publication.publication_workspace_id == "2024-S-123-456789"
        assert publication.notice_sub_type == "CONTRACT_NOTICE"
        assert publication.nuts_codes == ["BE21"]
        assert publication.ted_published is True

    def test_publication_deadline(self, db_session):
        """Test publication submission deadline."""
        future_date = datetime.now() + timedelta(days=30)
        publication = create_test_publication(
            db_session, vault_submission_deadline=future_date
        )

        assert publication.vault_submission_deadline > datetime.now()
        assert publication.vault_submission_deadline.date() == future_date.date()

    def test_publication_keywords(self, db_session):
        """Test publication extracted keywords."""
        keywords = ["road", "construction", "maintenance", "highway"]
        publication = create_test_publication(db_session, extracted_keywords=keywords)

        assert len(publication.extracted_keywords) == 4
        assert "construction" in publication.extracted_keywords
