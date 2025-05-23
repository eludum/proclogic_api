from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text, DateTime, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Address(Base):
    """Model for address information"""
    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    street: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    nuts_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    
    # For tracking purposes
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class Contact(Base):
    """Model for contact information"""
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    job_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # For tracking purposes
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class AppealsBodyContact(Base):
    """Model for appeals body contact information"""
    __tablename__ = "appeals_body_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # For tracking purposes
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class AppealsBody(Base):
    """Model for appeals body information"""
    __tablename__ = "appeals_bodies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    vat_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Relationships
    contact_id: Mapped[Optional[int]] = mapped_column(ForeignKey("appeals_body_contacts.id", ondelete="SET NULL"), nullable=True)
    contact = relationship("AppealsBodyContact", lazy="joined")
    
    address_id: Mapped[Optional[int]] = mapped_column(ForeignKey("addresses.id", ondelete="SET NULL"), nullable=True)
    address = relationship("Address", lazy="joined")
    
    # For tracking purposes
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class Organization(Base):
    """Model for organization information"""
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    vat_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Relationships
    contact_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    contact = relationship("Contact", lazy="joined")
    
    address_id: Mapped[Optional[int]] = mapped_column(ForeignKey("addresses.id", ondelete="SET NULL"), nullable=True)
    address = relationship("Address", lazy="joined")
    
    # For tracking purposes
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class Winner(Base):
    """Model for winning tenderer information"""
    __tablename__ = "winners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    vat_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    size: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tender_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    subcontracting: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Relationships
    address_id: Mapped[Optional[int]] = mapped_column(ForeignKey("addresses.id", ondelete="SET NULL"), nullable=True)
    address = relationship("Address", lazy="joined")
    
    # For tracking purposes
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class Award(Base):
    """Model for award information"""
    __tablename__ = "publication_awards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    publication_workspace_id: Mapped[str] = mapped_column(
        ForeignKey("publications.publication_workspace_id", ondelete="CASCADE"),
        index=True,
    )

    # Basic Information
    notice_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    contract_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    internal_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    issue_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notice_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Winner details (foreign key)
    winner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("winners.id", ondelete="SET NULL"), nullable=True)
    winner = relationship("Winner", lazy="joined")

    # Organization details (foreign key)
    organization_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    organization = relationship("Organization", lazy="joined")

    # Appeals body details (foreign key)
    appeals_body_id: Mapped[Optional[int]] = mapped_column(ForeignKey("appeals_bodies.id", ondelete="SET NULL"), nullable=True)
    appeals_body = relationship("AppealsBody", lazy="joined")

    # Award values
    award_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    award_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lowest_tender_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    highest_tender_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Tender process information
    tenders_received: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    participation_requests: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    electronic_auction_used: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    dynamic_purchasing_system: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    framework_agreement: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Contract details
    contract_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    contract_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contract_start_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    contract_end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Storage for original XML
    xml_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    publication = relationship("Publication", back_populates="award_data")
    suppliers = relationship(
        "AwardSupplier", back_populates="award", cascade="all, delete-orphan"
    )

    # Additional metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )


class AwardSupplier(Base):
    """Model for suppliers involved in an award"""
    __tablename__ = "award_suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    award_id: Mapped[int] = mapped_column(
        ForeignKey("publication_awards.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255))
    vat_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Relationships
    address_id: Mapped[Optional[int]] = mapped_column(ForeignKey("addresses.id", ondelete="SET NULL"), nullable=True)
    address = relationship("Address", lazy="joined")
    
    award = relationship("Award", back_populates="suppliers")
    
    # For tracking purposes
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    