from datetime import datetime, timedelta
from typing import Dict, List

import factory
from factory.alchemy import SQLAlchemyModelFactory
from faker import Faker

from app.models.company_models import Company, Sector
from app.models.publication_models import (
    CPVCode,
    Description,
    Dossier,
    Organisation,
    Publication,
)

fake = Faker()


class CompanyFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Company

    vat_number = factory.LazyFunction(lambda: f"BE{fake.numerify('##########')}")
    name = factory.Faker("company")
    emails = factory.LazyFunction(lambda: [fake.email() for _ in range(2)])
    subscription = "starter"
    number_of_employees = factory.Faker("random_int", min=1, max=1000)
    summary_activities = factory.Faker("text", max_nb_chars=500)
    max_publication_value = factory.Faker("random_int", min=10000, max=1000000)
    activity_keywords = factory.LazyFunction(lambda: [fake.word() for _ in range(5)])
    operating_regions = factory.LazyFunction(lambda: ["BE2", "BE3"])


class PublicationFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Publication

    publication_workspace_id = factory.LazyFunction(
        lambda: f"2024-S-{fake.numerify('###')}-{fake.numerify('######')}"
    )
    dispatch_date = factory.Faker(
        "date_time_between", start_date="-30d", end_date="now"
    )
    insertion_date = factory.Faker(
        "date_time_between", start_date="-30d", end_date="now"
    )
    publication_date = factory.Faker(
        "date_time_between", start_date="-30d", end_date="now"
    )
    natures = ["GENERAL"]
    notice_ids = factory.LazyFunction(lambda: [fake.uuid4() for _ in range(2)])
    notice_sub_type = "CONTRACT_NOTICE"
    nuts_codes = ["BE21", "BE211"]
    procedure_id = factory.Faker("uuid4")
    publication_languages = ["NL", "FR", "EN"]
    publication_reference_numbers_bda = factory.LazyFunction(
        lambda: [fake.numerify("BDA-2024-######")]
    )
    publication_type = "STANDARD"
    reference_number = factory.Faker("numerify", text="REF-####-####")
    ted_published = True
    vault_submission_deadline = factory.Faker(
        "date_time_between", start_date="+10d", end_date="+60d"
    )
    cpv_main_code_code = "45000000"
    organisation_id = 1
    dossier_reference_number = factory.Faker("numerify", text="DOS-####")


def create_test_company(session, **kwargs) -> Company:
    """Create a test company with default values."""
    company_data = {
        "vat_number": kwargs.get("vat_number", "BE0123456789"),
        "name": kwargs.get("name", "Test Company NV"),
        "emails": kwargs.get("emails", ["test@company.com", "admin@company.com"]),
        "subscription": kwargs.get("subscription", "starter"),
        "number_of_employees": kwargs.get("number_of_employees", 50),
        "summary_activities": kwargs.get(
            "summary_activities", "Construction and infrastructure development"
        ),
        "activity_keywords": kwargs.get(
            "activity_keywords", ["construction", "building", "infrastructure"]
        ),
        "operating_regions": kwargs.get("operating_regions", ["BE2", "BE21"]),
    }

    company = Company(**company_data)
    session.add(company)
    session.commit()
    return company


def create_test_publication(session, **kwargs) -> Publication:
    """Create a test publication with default values."""
    # First create required related objects
    cpv_code = CPVCode(code=kwargs.get("cpv_code", "45000000"))
    session.add(cpv_code)

    dossier = Dossier(
        reference_number=kwargs.get("dossier_ref", "DOS-2024-001"),
        legal_basis="DIRECTIVE_2014_24_EU",
        number="001",
        procurement_procedure_type="OPEN",
    )
    session.add(dossier)

    organisation = Organisation(organisation_id=1, tree="BE.GOV")
    session.add(organisation)

    session.flush()

    publication_data = {
        "publication_workspace_id": kwargs.get(
            "publication_workspace_id", "2024-S-123-456789"
        ),
        "dispatch_date": kwargs.get("dispatch_date", datetime.now()),
        "insertion_date": kwargs.get("insertion_date", datetime.now()),
        "publication_date": kwargs.get("publication_date", datetime.now()),
        "natures": kwargs.get("natures", ["GENERAL"]),
        "notice_ids": kwargs.get("notice_ids", ["notice-123"]),
        "notice_sub_type": kwargs.get("notice_sub_type", "CONTRACT_NOTICE"),
        "nuts_codes": kwargs.get("nuts_codes", ["BE21"]),
        "procedure_id": kwargs.get("procedure_id", "proc-123"),
        "publication_languages": kwargs.get("publication_languages", ["NL", "FR"]),
        "publication_reference_numbers_bda": kwargs.get(
            "publication_reference_numbers_bda", ["BDA-2024-123456"]
        ),
        "publication_type": kwargs.get("publication_type", "STANDARD"),
        "reference_number": kwargs.get("reference_number", "REF-2024-001"),
        "ted_published": kwargs.get("ted_published", True),
        "vault_submission_deadline": kwargs.get(
            "vault_submission_deadline", datetime.now() + timedelta(days=30)
        ),
        "cpv_main_code_code": cpv_code.code,
        "organisation_id": organisation.organisation_id,
        "dossier_reference_number": dossier.reference_number,
        "estimated_value": kwargs.get("estimated_value", 500000),
        "extracted_keywords": kwargs.get(
            "extracted_keywords", ["construction", "highway", "maintenance"]
        ),
    }

    publication = Publication(**publication_data)
    session.add(publication)
    session.commit()
    return publication
