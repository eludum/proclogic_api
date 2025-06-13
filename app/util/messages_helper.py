from datetime import datetime

import app.crud.company as crud_company
import app.crud.notification as crud_notification
from app.config.postgres import get_session


def smart_truncate_publication_title(
    publication_title: str, max_length: int = 200
) -> str:
    """
    Smart truncation for publication titles, preserving meaning by cutting at word boundaries.
    Leaves room for the notification suffix text.
    """
    if len(publication_title) <= max_length:
        return publication_title

    # Try to truncate at word boundary
    truncated = publication_title[: max_length - 3]
    last_space = truncated.rfind(" ")

    # Only use word boundary if we don't lose too much content (more than 80% retained)
    if last_space > max_length * 0.8:
        truncated = truncated[:last_space]

    return truncated + "..."


async def send_recommendation_notification(
    company_vat_number: str,
    publication_id: str,
    publication_title: str,
    publication_submission_deadline: datetime,
):
    """Send a recommendation notification to a company."""
    with get_session() as session:
        company = crud_company.get_company_by_vat_number(company_vat_number, session)
        if not company:
            return False

        # Truncate only the publication title, leaving room for the suffix
        truncated_title = smart_truncate_publication_title(publication_title)
        
        crud_notification.create_notification(
            title=f"'{truncated_title}' is aanbevolen voor jou door Procy",
            content=f"Wees er snel bij, inschrijven kan nog tot {publication_submission_deadline}",
            notification_type="recommendation",
            company_vat_number=company_vat_number,
            link=f"/publications/detail/{publication_id}",
            related_entity_id=publication_id,
            session=session,
        )

        return True


async def send_deadline_notification(
    company_vat_number: str, publication_id: str, publication_title: str, days_left: int
):
    """Send a deadline notification to a company."""
    with get_session() as session:
        company = crud_company.get_company_by_vat_number(company_vat_number, session)
        if not company:
            return False

        crud_notification.create_notification(
            title=f"Deadline nadert voor '{publication_title}'",
            content=f"Je hebt nog {days_left} dag(en) om je inschrijving in te dienen.",
            notification_type="deadline",
            company_vat_number=company_vat_number,
            link=f"/publications/detail/{publication_id}",
            related_entity_id=publication_id,
            session=session,
        )

        return True


async def send_system_notification(
    company_vat_number: str, title: str, content: str, link: str = None
):
    """Send a system notification to a company."""
    with get_session() as session:
        company = crud_company.get_company_by_vat_number(company_vat_number, session)
        if not company:
            return False

        crud_notification.create_notification(
            title=title,
            content=content,
            notification_type="system",
            company_vat_number=company_vat_number,
            link=link,
            session=session,
        )

        return True


async def send_forum_notification(
    company_vat_number: str, thread_id: str, thread_title: str
):
    """Send a forum notification to a company."""
    with get_session() as session:
        company = crud_company.get_company_by_vat_number(company_vat_number, session)
        if not company:
            return False

        crud_notification.create_notification(
            title="Nieuwe reactie in forum",
            content=f"Er is een nieuwe reactie geplaatst in het forum over '{thread_title}'.",
            notification_type="forum",
            company_vat_number=company_vat_number,
            link=f"/forum/thread/{thread_id}",
            related_entity_id=thread_id,
            session=session,
        )

        return True
