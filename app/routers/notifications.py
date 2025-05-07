from typing import List

import app.crud.company as crud_company
import app.crud.notification as crud_notification
from app.config.postgres import get_session
from app.schemas.notification_schemas import (
    NotificationCreate,
    NotificationListResponse,
    NotificationResponse,
)
from app.util.clerk import AuthUser, get_auth_user
from fastapi import APIRouter, Depends, HTTPException, Path, Query

notifications_router = APIRouter()


@notifications_router.get("/notifications/", response_model=NotificationListResponse)
async def get_notifications(
    limit: int = Query(100, description="Maximum number of notifications to return"),
    offset: int = Query(0, description="Skip this many notifications"),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Get all notifications for the authenticated user's company."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Get notifications for this company
        notifications, total, unread = crud_notification.get_notifications_for_company(
            company_vat_number=company.vat_number,
            session=session,
            limit=limit,
            offset=offset,
        )

        # Convert to response schema
        notification_responses = [
            NotificationResponse(
                id=notification.id,
                title=notification.title,
                content=notification.content,
                notification_type=notification.notification_type,
                is_read=notification.is_read,
                created_at=notification.created_at,
                link=notification.link,
                related_entity_id=notification.related_entity_id,
                company_vat_number=notification.company_vat_number,
            )
            for notification in notifications
        ]

        return NotificationListResponse(
            items=notification_responses, total=total, unread=unread
        )


@notifications_router.post("/notifications/", response_model=NotificationResponse)
async def create_new_notification(
    notification: NotificationCreate,
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Create a new notification."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Verify company matches the authenticated user's company
        if notification.company_vat_number != company.vat_number:
            raise HTTPException(
                status_code=403,
                detail="Cannot create notifications for other companies",
            )

        # Create notification
        new_notification = crud_notification.create_notification(
            title=notification.title,
            content=notification.content,
            notification_type=notification.notification_type,
            company_vat_number=company.vat_number,
            link=notification.link,
            related_entity_id=notification.related_entity_id,
            session=session,
        )

        return NotificationResponse(
            id=new_notification.id,
            title=new_notification.title,
            content=new_notification.content,
            notification_type=new_notification.notification_type,
            is_read=new_notification.is_read,
            created_at=new_notification.created_at,
            link=new_notification.link,
            related_entity_id=new_notification.related_entity_id,
            company_vat_number=new_notification.company_vat_number,
        )


@notifications_router.post(
    "/notifications/{notification_id}/read", response_model=NotificationResponse
)
async def mark_notification_read(
    notification_id: int = Path(
        ..., description="The ID of the notification to mark as read"
    ),
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Mark a notification as read."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        notification = crud_notification.mark_notification_as_read(
            notification_id=notification_id, session=session
        )

        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")

        # Verify ownership
        if notification.company_vat_number != company.vat_number:
            raise HTTPException(
                status_code=403, detail="Unauthorized access to notification"
            )

        return NotificationResponse(
            id=notification.id,
            title=notification.title,
            content=notification.content,
            notification_type=notification.notification_type,
            is_read=notification.is_read,
            created_at=notification.created_at,
            link=notification.link,
            related_entity_id=notification.related_entity_id,
            company_vat_number=notification.company_vat_number,
        )


@notifications_router.post("/notifications/mark-read", status_code=200)
async def mark_notifications_read(
    notification_ids: List[int],
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Mark multiple notifications as read."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Verify ownership of all notifications
        for notification_id in notification_ids:
            notification = (
                session.query(crud_notification.Notification)
                .filter(crud_notification.Notification.id == notification_id)
                .first()
            )

            if notification and notification.company_vat_number != company.vat_number:
                raise HTTPException(
                    status_code=403,
                    detail=f"Unauthorized access to notification {notification_id}",
                )

        success = crud_notification.mark_notifications_as_read(
            notification_ids=notification_ids, session=session
        )

        if not success:
            raise HTTPException(status_code=404, detail="No notifications were updated")

        return {"message": "Notifications marked as read"}


@notifications_router.post("/notifications/delete", status_code=200)
async def delete_notifications_bulk(
    notification_ids: List[int],
    auth_user: AuthUser = Depends(get_auth_user),
):
    """Delete multiple notifications."""
    if not auth_user.email:
        raise HTTPException(status_code=400, detail="User email not available")

    with get_session() as session:
        company = crud_company.get_company_by_email(
            email=auth_user.email, session=session
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Verify ownership of all notifications
        for notification_id in notification_ids:
            notification = (
                session.query(crud_notification.Notification)
                .filter(crud_notification.Notification.id == notification_id)
                .first()
            )

            if notification and notification.company_vat_number != company.vat_number:
                raise HTTPException(
                    status_code=403,
                    detail=f"Unauthorized access to notification {notification_id}",
                )

        success = crud_notification.delete_notifications(
            notification_ids=notification_ids, session=session
        )

        if not success:
            raise HTTPException(status_code=404, detail="No notifications were deleted")

        return {"message": "Notifications deleted"}
