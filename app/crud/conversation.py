import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.conversation_models import Conversation, Message


def get_or_create_conversation(
    company_vat_number: str,
    publication_workspace_id: str,
    session: Session,
) -> Conversation:
    """Get or create a conversation between a company and a publication."""
    conversation = (
        session.query(Conversation)
        .filter(
            Conversation.company_vat_number == company_vat_number,
            Conversation.publication_workspace_id == publication_workspace_id,
            Conversation.is_active == True,
        )
        .first()
    )
    
    if not conversation:
        conversation = Conversation(
            company_vat_number=company_vat_number,
            publication_workspace_id=publication_workspace_id,
            is_active=True,
        )
        session.add(conversation)
        session.commit()
        
    return conversation


def get_conversation_by_id(conversation_id: int, session: Session) -> Optional[Conversation]:
    """Get conversation by ID with all messages."""
    return (
        session.query(Conversation)
        .filter(Conversation.id == conversation_id)
        .options(joinedload(Conversation.messages))
        .first()
    )


def get_company_conversations(company_vat_number: str, session: Session) -> List[Conversation]:
    """Get all conversations for a company."""
    return (
        session.query(Conversation)
        .filter(Conversation.company_vat_number == company_vat_number)
        .order_by(Conversation.updated_at.desc())
        .options(joinedload(Conversation.publication))
        .all()
    )


def get_publication_conversations(publication_workspace_id: str, session: Session) -> List[Conversation]:
    """Get all conversations for a publication."""
    return (
        session.query(Conversation)
        .filter(Conversation.publication_workspace_id == publication_workspace_id)
        .order_by(Conversation.updated_at.desc())
        .options(joinedload(Conversation.company))
        .all()
    )


def add_message(
    conversation_id: int, 
    role: str, 
    content: str, 
    citations: Optional[str] = None,
    session: Session = None
) -> Message:
    """Add a message to a conversation."""
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        citations=citations,
    )
    session.add(message)
    
    # Update conversation's updated_at timestamp
    conversation = session.query(Conversation).filter(Conversation.id == conversation_id).first()
    conversation.updated_at = datetime.now()
    
    session.commit()
    return message


def get_conversation_messages(conversation_id: int, session: Session) -> List[Message]:
    """Get all messages for a conversation, ordered chronologically."""
    return (
        session.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .all()
    )




def deactivate_conversation(conversation_id: int, session: Session) -> bool:
    """Deactivate a conversation."""
    try:
        conversation = session.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conversation:
            return False
            
        conversation.is_active = False
        session.commit()
        return True
    except Exception as e:
        logging.error(f"Error deactivating conversation: {e}")
        session.rollback()
        return False