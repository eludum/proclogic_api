"""Company-supplied award data, kept strictly separate from the BOSA rows.

Awards in `contracts`/`publications` are scraped from BOSA and shared by every
customer, so nothing a user types may ever be written back to them: one
customer's guess would become everyone's data, and the next scraper run would
silently overwrite it either way.

Instead a company records its own values here and the detail view resolves each
field as "the company's value if it has one, otherwise BOSA's". That keeps the
scraped row authoritative and reversible -- deleting the entry restores the
original view -- and it keeps one company's corrections invisible to every other.

Two shapes share the table:

* ``publication_workspace_id`` set -- an overlay on an existing BOSA award,
  filling in what BOSA left blank (values are missing on a great many awards) or
  correcting what it got wrong.
* ``publication_workspace_id`` NULL -- an award the company entered itself,
  which BOSA never published. Postgres treats NULLs as distinct in a unique
  index, so a company can have many of these while still being limited to one
  overlay per BOSA award.

Every column except the keys is nullable on purpose: an entry records only the
fields the company actually supplied, so an untouched field keeps falling
through to BOSA rather than being overwritten with a blank.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# How the values got here. Recorded because a figure a person typed off the
# award notice and a figure a model read off a scan do not deserve equal trust,
# and the UI labels them differently.
SOURCE_MANUAL = "manual"
SOURCE_PDF = "pdf"

# The fields a company may supply. Deliberately the small set the awards UI
# actually shows, not every column on Contract: this is for completing a
# gunning, not for rewriting the procurement record.
OVERRIDABLE_FIELDS = (
    "title",
    "award_date",
    "winner",
    "buyer",
    "value",
    "currency",
    "reference_number",
    "notes",
)


class CompanyAwardEntry(Base):
    __tablename__ = "company_award_entries"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)

    # Scope. Both are set from the authenticated caller, never from the request
    # body -- see _require_company() in the router.
    company_vat_number: Mapped[str] = mapped_column(
        ForeignKey("companies.vat_number", ondelete="CASCADE"), nullable=False
    )
    created_by_email: Mapped[str] = mapped_column(String(320), nullable=False)

    # NULL for an award the company created itself.
    publication_workspace_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("publications.publication_workspace_id", ondelete="CASCADE"),
        nullable=True,
    )

    source: Mapped[str] = mapped_column(String(16), nullable=False, default=SOURCE_MANUAL)
    source_document_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Supplied values. All nullable: absent means "fall through to BOSA".
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    award_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    winner: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    buyer: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    reference_number: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # One overlay per company per BOSA award. NULLs compare as distinct, so
        # this does not limit how many awards a company may create itself.
        UniqueConstraint(
            "company_vat_number",
            "publication_workspace_id",
            name="uq_company_award_entry_scope",
        ),
    )

    def supplied(self) -> dict:
        """The fields this entry actually carries, for merging over a BOSA row."""
        return {
            field: getattr(self, field)
            for field in OVERRIDABLE_FIELDS
            if getattr(self, field) is not None
        }


# Every read is "this company's entries", so the company leads the index. The
# second covers the per-publication lookup the detail view does.
Index(
    "idx_company_award_entry_company",
    CompanyAwardEntry.company_vat_number,
    CompanyAwardEntry.publication_workspace_id,
)
