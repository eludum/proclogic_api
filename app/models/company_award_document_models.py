"""Documents a company attaches to an award.

Separate from the BOSA annexes, which are fetched live from the procurement API
and belong to everyone. These are the customer's own files -- their offer, the
award letter they received, internal notes as a PDF -- and like everything else
in company_award_entries they are visible only to the company that uploaded
them.

**Why the bytes live in Postgres.** There is no object store in this stack, and
pod filesystems are ephemeral: /code is replaced on every deploy and the
ephemeral-storage limit is there to stop a pod filling its node. That leaves the
database. It is the right call at this size -- a few small PDFs per award, capped
at 15 MB each -- and it keeps the file inside the same transaction and the same
backup as the row that owns it, with no second system to authorise against.

The bytes sit in their own table, and ``data`` is deferred, so listing a
company's uploads never drags the file contents along. If this ever outgrows
Postgres, the move is to read these rows out into a bucket and swap the column
for a key; nothing else needs to know.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    func,
)
from sqlalchemy.orm import Mapped, backref, deferred, mapped_column, relationship

from app.models.base import Base

# Per file. Award notices and offers are a few pages; this exists so a stray
# upload is refused at the door rather than after it has been read into memory.
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


class CompanyAwardDocument(Base):
    __tablename__ = "company_award_documents"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)

    # Hangs off the company's entry for this award, so it inherits that row's
    # ownership: there is no company column to forget to filter on, and deleting
    # the entry takes its files with it.
    award_entry_id: Mapped[int] = mapped_column(
        ForeignKey("company_award_entries.id", ondelete="CASCADE"), nullable=False
    )

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by_email: Mapped[str] = mapped_column(String(320), nullable=False)

    # Deferred: a listing wants filenames and sizes, not megabytes of PDF.
    data: Mapped[bytes] = deferred(mapped_column(LargeBinary, nullable=False))

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # passive_deletes lets the database's ON DELETE CASCADE do the work.
    # Without it SQLAlchemy "helpfully" UPDATEs award_entry_id to NULL before
    # deleting the parent, which the NOT NULL constraint rejects -- so removing
    # a company's data for an award failed outright instead of taking its files
    # with it.
    entry = relationship(
        "CompanyAwardEntry",
        backref=backref(
            "documents", cascade="all, delete-orphan", passive_deletes=True
        ),
    )


Index("idx_company_award_document_entry", CompanyAwardDocument.award_entry_id)
