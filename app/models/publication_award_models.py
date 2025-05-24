from sqlalchemy import (
    create_engine,
    Column,
    String,
    Integer,
    Float,
    Boolean,
    Date,
    ForeignKey,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Address(Base):
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True)
    street = Column(String(255))
    city = Column(String(100))
    postal_code = Column(String(20))
    country = Column(String(100))
    nuts_code = Column(String(10))

    # Relationships
    organizations = relationship("Organization", back_populates="address")


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    business_id = Column(String(50), unique=True)
    website = Column(String(255))
    phone = Column(String(50))
    email = Column(String(255))
    company_size = Column(String(50))
    subcontracting = Column(String(100))

    # Foreign Keys
    address_id = Column(Integer, ForeignKey("addresses.id"))

    # Relationships
    address = relationship("Address", back_populates="organizations")
    contracts_as_authority = relationship(
        "Contract",
        foreign_keys="Contract.contracting_authority_id",
        back_populates="contracting_authority",
    )
    contracts_as_winner = relationship(
        "Contract",
        foreign_keys="Contract.winning_tenderer_id",
        back_populates="winning_tenderer",
    )
    contracts_as_appeals_body = relationship(
        "Contract",
        foreign_keys="Contract.appeals_body_id",
        back_populates="appeals_body",
    )
    contracts_as_service_provider = relationship(
        "Contract",
        foreign_keys="Contract.service_provider_id",
        back_populates="service_provider",
    )
    contact_persons = relationship("ContactPerson", back_populates="organization")


class ContactPerson(Base):
    __tablename__ = "contact_persons"

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    job_title = Column(String(255))
    phone = Column(String(50))
    email = Column(String(255))

    # Foreign Keys
    organization_id = Column(Integer, ForeignKey("organizations.id"))

    # Relationships
    organization = relationship("Organization", back_populates="contact_persons")


class Contract(Base):
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True)
    notice_id = Column(String(100), unique=True, nullable=False)
    contract_id = Column(String(100), unique=True, nullable=False)
    internal_id = Column(String(255), unique=True)
    issue_date = Column(Date)
    notice_type = Column(String(100))

    # Financial Information
    total_contract_amount = Column(Float)
    currency = Column(String(3))
    lowest_publication_amount = Column(Float)
    highest_publication_amount = Column(Float)

    # Publication Process Information
    number_of_publications_received = Column(Integer)
    number_of_participation_requests = Column(Integer)
    electronic_auction_used = Column(Boolean)
    dynamic_purchasing_system = Column(String(50))
    framework_agreement = Column(String(50))

    # Foreign Keys
    contracting_authority_id = Column(Integer, ForeignKey("organizations.id"))
    winning_publisher_id = Column(Integer, ForeignKey("organizations.id"))
    appeals_body_id = Column(Integer, ForeignKey("organizations.id"))
    service_provider_id = Column(Integer, ForeignKey("organizations.id"))

    # Relationships
    contracting_authority = relationship(
        "Organization",
        foreign_keys=[contracting_authority_id],
        back_populates="contracts_as_authority",
    )
    winning_publisher = relationship(
        "Organization",
        foreign_keys=[winning_publisher_id],
        back_populates="contracts_as_winner",
    )
    appeals_body = relationship(
        "Organization",
        foreign_keys=[appeals_body_id],
        back_populates="contracts_as_appeals_body",
    )
    service_provider = relationship(
        "Organization",
        foreign_keys=[service_provider_id],
        back_populates="contracts_as_service_provider",
    )
