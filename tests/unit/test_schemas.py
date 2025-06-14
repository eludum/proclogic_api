import pytest
from datetime import datetime
from pydantic import ValidationError

from app.schemas.company_schemas import CompanySchema, CompanyUpdateSchema, SectorSchema
from app.schemas.publication_schemas import (
    PublicationSchema,
    CPVCodeSchema,
    DescriptionSchema,
)
from app.schemas.conversation_schemas import ChatRequest, ChatResponse


class TestCompanySchemas:
    def test_company_schema_validation(self):
        """Test company schema validation."""
        valid_data = {
            "vat_number": "BE0123456789",
            "name": "Test Company",
            "emails": ["test@example.com"],
            "subscription": "starter",
            "number_of_employees": 50,
            "summary_activities": "Test activities",
            "interested_sectors": [],
        }

        schema = CompanySchema(**valid_data)
        assert schema.vat_number == "BE0123456789"
        assert schema.subscription == "starter"

    def test_company_schema_invalid_subscription(self):
        """Test invalid subscription type."""
        invalid_data = {
            "vat_number": "BE0123456789",
            "name": "Test Company",
            "emails": ["test@example.com"],
            "subscription": "invalid_type",  # Should be starter/team/custom
            "number_of_employees": 50,
            "summary_activities": "Test activities",
        }

        with pytest.raises(ValidationError):
            CompanySchema(**invalid_data)

    def test_sector_schema(self):
        """Test sector schema."""
        sector_data = {
            "sector": "Construction",
            "cpv_codes": ["45000000", "45100000", "45200000"],
        }

        schema = SectorSchema(**sector_data)
        assert schema.sector == "Construction"
        assert len(schema.cpv_codes) == 3

    def test_company_update_schema_partial(self):
        """Test partial company update."""
        update_data = {"number_of_employees": 75, "max_publication_value": 1000000}

        schema = CompanyUpdateSchema(**update_data)
        assert schema.number_of_employees == 75
        assert schema.max_publication_value == 1000000
        assert schema.name is None  # Not provided


class TestPublicationSchemas:
    def test_cpv_code_schema(self):
        """Test CPV code schema."""
        cpv_data = {
            "code": "45000000",
            "descriptions": [
                {"language": "EN", "text": "Construction work"},
                {"language": "NL", "text": "Bouwwerkzaamheden"},
            ],
        }

        schema = CPVCodeSchema(**cpv_data)
        assert schema.code == "45000000"
        assert len(schema.descriptions) == 2

    def test_description_schema(self):
        """Test description schema."""
        desc_data = {
            "language": "EN",
            "text": "Highway construction and maintenance services",
        }

        schema = DescriptionSchema(**desc_data)
        assert schema.language == "EN"
        assert "Highway" in schema.text


class TestConversationSchemas:
    def test_chat_request_schema(self):
        """Test chat request schema."""
        request_data = {"message": "Tell me about this tender", "conversation_id": 123}

        schema = ChatRequest(**request_data)
        assert schema.message == "Tell me about this tender"
        assert schema.conversation_id == 123

    def test_chat_response_schema(self):
        """Test chat response schema."""
        response_data = {
            "response": "This tender is about highway construction...",
            "citations": "[1] Document reference",
        }

        schema = ChatResponse(**response_data)
        assert "highway construction" in schema.response
        assert schema.citations is not None
