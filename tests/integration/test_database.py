import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.company_models import Company
from app.models.publication_models import Publication, CompanyPublicationMatch
from tests.fixtures.test_data import create_test_company, create_test_publication


class TestDatabaseIntegration:
    def test_database_connection(self, db_session):
        """Test database connection and basic operations."""
        # Test write
        company = Company(
            vat_number="BE1111111111",
            name="DB Test Company",
            emails=["db@test.com"],
            subscription="starter",
            number_of_employees=10,
            summary_activities="Testing database"
        )
        db_session.add(company)
        db_session.commit()
        
        # Test read
        result = db_session.execute(
            select(Company).where(Company.vat_number == "BE1111111111")
        ).scalar_one_or_none()
        
        assert result is not None
        assert result.name == "DB Test Company"
        
    def test_unique_constraint(self, db_session):
        """Test unique constraints are enforced."""
        company1 = create_test_company(db_session, vat_number="BE2222222222")
        
        # Try to create another company with same VAT
        company2 = Company(
            vat_number="BE2222222222",  # Same VAT
            name="Another Company",
            emails=["another@test.com"],
            subscription="starter",
            number_of_employees=5,
            summary_activities="Testing"
        )
        
        with pytest.raises(IntegrityError):
            db_session.add(company2)
            db_session.commit()
            
    def test_cascade_delete(self, db_session):
        """Test cascade delete operations."""
        company = create_test_company(db_session)
        publication = create_test_publication(db_session)
        
        # Create a match
        match = CompanyPublicationMatch(
            company_vat_number=company.vat_number,
            publication_workspace_id=publication.publication_workspace_id,
            match_percentage=75.0
        )
        db_session.add(match)
        db_session.commit()
        
        # Delete company
        db_session.delete(company)
        db_session.commit()
        
        # Check match is also deleted
        remaining_matches = db_session.execute(
            select(CompanyPublicationMatch).where(
                CompanyPublicationMatch.company_vat_number == company.vat_number
            )
        ).scalars().all()
        
        assert len(remaining_matches) == 0
        
    def test_transaction_rollback(self, db_session):
        """Test transaction rollback."""
        initial_count = db_session.execute(
            select(Company)
        ).scalars().all()
        
        try:
            company = Company(
                vat_number="BE3333333333",
                name="Rollback Test",
                emails=["rollback@test.com"],
                subscription="invalid_subscription",  # This should fail
                number_of_employees=10,
                summary_activities="Testing rollback"
            )
            db_session.add(company)
            db_session.commit()
        except:
            db_session.rollback()
            
        # Check no company was added
        final_count = db_session.execute(
            select(Company)
        ).scalars().all()
        
        assert len(final_count) == len(initial_count)