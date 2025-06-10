from datetime import datetime
from sqlalchemy import (
    DateTime,
    Integer,
    String,
    ForeignKey,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)
from app.models.base import Base

class ContractAddress(Base):
    __tablename__ = "contract_addresses"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    street: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(100))
    postal_code: Mapped[str] = mapped_column(String(20))
    country: Mapped[str] = mapped_column(String(100))
    nuts_code: Mapped[str] = mapped_column(String(10))

    # Relationships
    organizations: Mapped[list["ContractOrganization"]] = relationship(
        back_populates="address"
    )


class ContractOrganization(Base):
    __tablename__ = "contract_organizations"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_id: Mapped[str] = mapped_column(String(50), unique=True)
    website: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(255))
    company_size: Mapped[str] = mapped_column(String(50))
    subcontracting: Mapped[str] = mapped_column(String(100))

    address_id: Mapped[int] = mapped_column(ForeignKey("contract_addresses.id"))

    # Relationships
    address: Mapped["ContractAddress"] = relationship(back_populates="organizations")
    contracts_as_authority: Mapped[list["Contract"]] = relationship(
        back_populates="contracting_authority",
        foreign_keys="Contract.contracting_authority_id",
    )
    contracts_as_winner: Mapped[list["Contract"]] = relationship(
        back_populates="winning_publisher",
        foreign_keys="Contract.winning_publisher_id",
    )
    contracts_as_appeals_body: Mapped[list["Contract"]] = relationship(
        back_populates="appeals_body",
        foreign_keys="Contract.appeals_body_id",
    )
    contracts_as_service_provider: Mapped[list["Contract"]] = relationship(
        back_populates="service_provider",
        foreign_keys="Contract.service_provider_id",
    )
    contact_persons: Mapped[list["ContractContactPerson"]] = relationship(
        back_populates="organization"
    )


class ContractContactPerson(Base):
    __tablename__ = "contract_contact_persons"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    job_title: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(255))

    organization_id: Mapped[int] = mapped_column(ForeignKey("contract_organizations.id"))

    # Relationships
    organization: Mapped["ContractOrganization"] = relationship(
        back_populates="contact_persons"
    )


class Contract(Base):
    __tablename__ = "contracts"

    notice_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    contract_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, primary_key=True)
    internal_id: Mapped[str] = mapped_column(String(255), unique=True)
    issue_date: Mapped[datetime] = mapped_column(DateTime)
    notice_type: Mapped[str] = mapped_column(String(100))

    # Financial Information
    total_contract_amount: Mapped[float]
    currency: Mapped[str] = mapped_column(String(3))
    lowest_publication_amount: Mapped[float]
    highest_publication_amount: Mapped[float]

    # Publication Process Information
    number_of_publications_received: Mapped[int]
    number_of_participation_requests: Mapped[int]
    electronic_auction_used: Mapped[bool]
    dynamic_purchasing_system: Mapped[str] = mapped_column(String(50))
    framework_agreement: Mapped[str] = mapped_column(String(50))

    # Foreign Keys
    contracting_authority_id: Mapped[int] = mapped_column(ForeignKey("contract_organizations.id"))
    winning_publisher_id: Mapped[int] = mapped_column(ForeignKey("contract_organizations.id"))
    appeals_body_id: Mapped[int] = mapped_column(ForeignKey("contract_organizations.id"))
    service_provider_id: Mapped[int] = mapped_column(ForeignKey("contract_organizations.id"))

    # Relationships
    contracting_authority: Mapped["ContractOrganization"] = relationship(
        foreign_keys=[contracting_authority_id],
        back_populates="contracts_as_authority",
    )
    winning_publisher: Mapped["ContractOrganization"] = relationship(
        foreign_keys=[winning_publisher_id],
        back_populates="contracts_as_winner",
    )
    appeals_body: Mapped["ContractOrganization"] = relationship(
        foreign_keys=[appeals_body_id],
        back_populates="contracts_as_appeals_body",
    )
    service_provider: Mapped["ContractOrganization"] = relationship(
        foreign_keys=[service_provider_id],
        back_populates="contracts_as_service_provider",
    )
