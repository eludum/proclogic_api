"""Who is asking.

Every tool call carries a ToolContext. Public procurement tools ignore it;
tenant-scoped tools use it to constrain what they return. It is always built
from a *verified* Clerk token -- never from anything the model produced, so the
model cannot talk its way into another company's data by claiming a VAT number.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from app.config.postgres import get_session
from app.crud import company as crud_company

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolContext:
    user_id: Optional[str] = None
    email: Optional[str] = None
    company_vat: Optional[str] = None
    company_name: Optional[str] = None

    @property
    def is_authenticated(self) -> bool:
        return bool(self.user_id)

    def require_company(self) -> str:
        """VAT number of the calling company, or raise.

        Tenant-scoped tools call this rather than silently returning everything
        when the context is empty -- an unscoped query is the failure mode that
        leaks data, so it has to be the loud one.
        """
        if not self.company_vat:
            raise PermissionError(
                "This tool requires an authenticated company context."
            )
        return self.company_vat


ANONYMOUS = ToolContext()


def build_context(user_id: str, email: Optional[str]) -> ToolContext:
    """Resolve a verified Clerk identity to the company it belongs to."""
    if not email:
        return ToolContext(user_id=user_id, email=email)

    try:
        with get_session() as session:
            company = crud_company.get_company_by_email(email=email, session=session)
            if company is None:
                return ToolContext(user_id=user_id, email=email)
            return ToolContext(
                user_id=user_id,
                email=email,
                company_vat=company.vat_number,
                company_name=company.name,
            )
    except Exception as exc:
        logger.warning("Could not resolve company for %s: %s", email, exc)
        return ToolContext(user_id=user_id, email=email)


async def build_context_async(user_id: str, email: Optional[str]) -> ToolContext:
    """build_context off the event loop.

    The company lookup is a synchronous database round-trip, and this runs on
    request paths -- including the MCP mount's auth middleware, which sits in
    front of every tool call.
    """
    return await asyncio.to_thread(build_context, user_id, email)
