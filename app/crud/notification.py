import logging
from datetime import datetime, timedelta
from typing import List, Optional

from app.models.notification_models import Notification
from sqlalchemy.orm import Session


def create_notification(
    title: str,
    content: str,
    notification_type: str,
    company_vat_number: str,
    session: Session,
    link: Optional[str] = None,
    related_entity_id: Optional[str] = None,
    is_read: bool = False,
) -> Notification:
    """Create a new notification for a company."""
    try:
        notification = Notification(
            title=title,
            content=content,
            notification_type=notification_type,
            company_vat_number=company_vat_number,
            link=link,
            related_entity_id=related_entity_id,
            is_read=is_read,
        )

        session.add(notification)
        session.commit()

        session.refresh(notification)
        return notification
    except Exception as e:
        logging.error(f"Error creating notification: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def get_notifications_for_company(
    company_vat_number: str, session: Session, limit: int = 100, offset: int = 0
) -> tuple[List[Notification], int, int]:
    """Get notifications for a specific company by VAT number."""
    try:
        total_count = (
            session.query(Notification)
            .filter(Notification.company_vat_number == company_vat_number)
            .count()
        )

        unread_count = (
            session.query(Notification)
            .filter(
                Notification.company_vat_number == company_vat_number,
                Notification.is_read == False,
            )
            .count()
        )

        notifications = (
            session.query(Notification)
            .filter(Notification.company_vat_number == company_vat_number)
            .order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return notifications, total_count, unread_count
    except Exception as e:
        logging.error(f"Error getting notifications for company: {e}")
        return [], 0, 0
    finally:
        session.close()


def mark_notification_as_read(
    notification_id: int, session: Session
) -> Optional[Notification]:
    """Mark a notification as read."""
    try:
        notification = (
            session.query(Notification)
            .filter(Notification.id == notification_id)
            .first()
        )
        if not notification:
            return None

        notification.is_read = True
        session.commit()

        session.refresh(notification)
        return notification
    except Exception as e:
        logging.error(f"Error marking notification as read: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def mark_notifications_as_read(notification_ids: List[int], session: Session) -> bool:
    """Mark multiple notifications as read."""
    try:
        updated = (
            session.query(Notification)
            .filter(Notification.id.in_(notification_ids))
            .update({Notification.is_read: True}, synchronize_session=False)
        )

        session.commit()
        return updated > 0
    except Exception as e:
        logging.error(f"Error marking notifications as read: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def delete_notification(notification_id: int, session: Session) -> bool:
    """Delete a notification."""
    try:
        notification = (
            session.query(Notification)
            .filter(Notification.id == notification_id)
            .first()
        )
        if not notification:
            return False

        session.delete(notification)
        session.commit()
        return True
    except Exception as e:
        logging.error(f"Error deleting notification: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def delete_notifications(notification_ids: List[int], session: Session) -> bool:
    """Delete multiple notifications."""
    try:
        deleted = (
            session.query(Notification)
            .filter(Notification.id.in_(notification_ids))
            .delete(synchronize_session=False)
        )

        session.commit()
        return deleted > 0
    except Exception as e:
        logging.error(f"Error deleting notifications: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def cleanup_old_notifications(session: Session, days_to_keep: int = 90) -> int:
    """
    Clean up old notifications to prevent database bloat.
    Can be called by the daily scanner for maintenance.
    """
    try:
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)

        deleted_count = (
            session.query(Notification)
            .filter(Notification.created_at < cutoff_date)
            .delete()
        )

        session.commit()
        return deleted_count

    except Exception as e:
        logging.error(f"Error cleaning up old notifications: {e}")
        session.rollback()
        return 0


def has_recent_deadline_notification(
    company_vat_number: str, publication_id: str, session: Session
) -> bool:
    """
    Check if a deadline notification was recently sent for a specific period.
    Used to avoid sending duplicate deadline notifications.
    """
    try:
        # Check for notifications sent in the last day for this specific deadline period
        cutoff_time = datetime.now() - timedelta(hours=24)

        existing_notification = (
            session.query(Notification)
            .filter(
                Notification.company_vat_number == company_vat_number,
                Notification.related_entity_id == publication_id,
                Notification.notification_type == "deadline",
                Notification.created_at >= cutoff_time,
            )
            .first()
        )

        return existing_notification is not None

    except Exception as e:
        logging.error(f"Error checking recent deadline notification: {e}")
        return False
