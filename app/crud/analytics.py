from typing import Optional, 

from sqlalchemy.orm import Session

from app.ai.recommend import extract_award_data_from_xml, summarize_publication_award
from app.config.settings import Settings
from app.models.analytics_models import (
    Address,
    AppealsBody,
    AppealsBodyContact,
    Award,
    AwardSupplier,
    Contact,
    Organization,
    Winner,
)

settings = Settings()


def create_award_from_xml(
    db: Session, xml_content: str, publication_workspace_id: str
) -> Optional[Award]:
    """
    Create an award record from XML content.
    Extracts data and creates records in the database.
    """
    extracted_data = extract_award_data_from_xml(xml_content)

    if not extracted_data or "award_data" not in extracted_data:
        # Try with AI fallback
        extracted_data = summarize_publication_award(xml_content)
        if not extracted_data:
            return None

    # Create nested objects first

    # 1. Winner and winner address
    winner_id = None
    if "winner" in extracted_data:
        winner_data = extracted_data["winner"].dict(exclude_unset=True)

        # Extract address data if present
        address_id = None
        if "address" in winner_data:
            address_data = winner_data.pop("address")
            address = Address(**address_data.dict(exclude_unset=True))
            db.add(address)
            db.flush()
            address_id = address.id

        # Create winner
        winner = Winner(**winner_data)
        if address_id:
            winner.address_id = address_id

        db.add(winner)
        db.flush()
        winner_id = winner.id

    # 2. Organization, contact, and address
    organization_id = None
    if "organization" in extracted_data:
        org_data = extracted_data["organization"].dict(exclude_unset=True)

        # Extract contact data if present
        contact_id = None
        if "contact" in org_data:
            contact_data = org_data.pop("contact")
            contact = Contact(**contact_data.dict(exclude_unset=True))
            db.add(contact)
            db.flush()
            contact_id = contact.id

        # Extract address data if present
        address_id = None
        if "address" in org_data:
            address_data = org_data.pop("address")
            address = Address(**address_data.dict(exclude_unset=True))
            db.add(address)
            db.flush()
            address_id = address.id

        # Create organization
        organization = Organization(**org_data)
        if contact_id:
            organization.contact_id = contact_id
        if address_id:
            organization.address_id = address_id

        db.add(organization)
        db.flush()
        organization_id = organization.id

    # 3. Appeals body, contact, and address
    appeals_body_id = None
    if "appeals_body" in extracted_data:
        appeals_data = extracted_data["appeals_body"].dict(exclude_unset=True)

        # Extract contact data if present
        contact_id = None
        if "contact" in appeals_data:
            contact_data = appeals_data.pop("contact")
            contact = AppealsBodyContact(**contact_data.dict(exclude_unset=True))
            db.add(contact)
            db.flush()
            contact_id = contact.id

        # Extract address data if present
        address_id = None
        if "address" in appeals_data:
            address_data = appeals_data.pop("address")
            address = Address(**address_data.dict(exclude_unset=True))
            db.add(address)
            db.flush()
            address_id = address.id

        # Create appeals body
        appeals_body = AppealsBody(**appeals_data)
        if contact_id:
            appeals_body.contact_id = contact_id
        if address_id:
            appeals_body.address_id = address_id

        db.add(appeals_body)
        db.flush()
        appeals_body_id = appeals_body.id

    # 4. Create the main award record
    award_data = extracted_data.get("award_data", {})
    award = Award(publication_workspace_id=publication_workspace_id, **award_data)

    # Set foreign keys
    if winner_id:
        award.winner_id = winner_id
    if organization_id:
        award.organization_id = organization_id
    if appeals_body_id:
        award.appeals_body_id = appeals_body_id

    # Add XML content
    award.xml_content = xml_content

    db.add(award)
    db.flush()

    # 5. Create suppliers
    if "suppliers" in extracted_data and extracted_data["suppliers"]:
        for supplier_data in extracted_data["suppliers"]:
            supplier_dict = supplier_data.dict(exclude_unset=True)

            # Extract address data if present
            address_id = None
            if "address" in supplier_dict:
                address_data = supplier_dict.pop("address")
                address = Address(**address_data.dict(exclude_unset=True))
                db.add(address)
                db.flush()
                address_id = address.id

            # Create supplier
            supplier = AwardSupplier(award_id=award.id, **supplier_dict)
            if address_id:
                supplier.address_id = address_id

            db.add(supplier)

    db.commit()
    return award


def update_award_from_xml(
    db: Session, award_id: int, xml_content: str
) -> Optional[Award]:
    """
    Update an existing award record from XML content.
    Preserves existing records where possible and updates with new information.
    """
    # Get the existing award
    award = db.query(Award).filter(Award.id == award_id).first()
    if not award:
        return None

    # Extract data from XML
    extracted_data = extract_award_data_from_xml(xml_content)
    if not extracted_data or "award_data" not in extracted_data:
        # Try with AI fallback
        extracted_data = summarize_publication_award(xml_content)
        if not extracted_data:
            return None

    # Update nested objects first

    # 1. Winner and address
    if "winner" in extracted_data:
        winner_data = extracted_data["winner"].dict(exclude_unset=True)
        address_data = None

        if "address" in winner_data:
            address_data = winner_data.pop("address")

        # Update or create winner
        if award.winner_id:
            # Update existing winner
            winner = db.query(Winner).filter(Winner.id == award.winner_id).first()

            # Update fields
            for key, value in winner_data.items():
                setattr(winner, key, value)

            # Update address
            if address_data and winner.address_id:
                address = (
                    db.query(Address).filter(Address.id == winner.address_id).first()
                )
                for key, value in address_data.dict(exclude_unset=True).items():
                    setattr(address, key, value)
            elif address_data:
                # Create new address
                address = Address(**address_data.dict(exclude_unset=True))
                db.add(address)
                db.flush()
                winner.address_id = address.id
        else:
            # Create new winner
            winner = Winner(**winner_data)

            # Create address if needed
            if address_data:
                address = Address(**address_data.dict(exclude_unset=True))
                db.add(address)
                db.flush()
                winner.address_id = address.id

            db.add(winner)
            db.flush()
            award.winner_id = winner.id

    # 2. Organization, contact, and address
    if "organization" in extracted_data:
        org_data = extracted_data["organization"].dict(exclude_unset=True)
        contact_data = None
        address_data = None

        if "contact" in org_data:
            contact_data = org_data.pop("contact")

        if "address" in org_data:
            address_data = org_data.pop("address")

        # Update or create organization
        if award.organization_id:
            # Update existing organization
            organization = (
                db.query(Organization)
                .filter(Organization.id == award.organization_id)
                .first()
            )

            # Update fields
            for key, value in org_data.items():
                setattr(organization, key, value)

            # Update contact
            if contact_data and organization.contact_id:
                contact = (
                    db.query(Contact)
                    .filter(Contact.id == organization.contact_id)
                    .first()
                )
                for key, value in contact_data.dict(exclude_unset=True).items():
                    setattr(contact, key, value)
            elif contact_data:
                # Create new contact
                contact = Contact(**contact_data.dict(exclude_unset=True))
                db.add(contact)
                db.flush()
                organization.contact_id = contact.id

            # Update address
            if address_data and organization.address_id:
                address = (
                    db.query(Address)
                    .filter(Address.id == organization.address_id)
                    .first()
                )
                for key, value in address_data.dict(exclude_unset=True).items():
                    setattr(address, key, value)
            elif address_data:
                # Create new address
                address = Address(**address_data.dict(exclude_unset=True))
                db.add(address)
                db.flush()
                organization.address_id = address.id
        else:
            # Create new organization
            organization = Organization(**org_data)

            # Create contact if needed
            if contact_data:
                contact = Contact(**contact_data.dict(exclude_unset=True))
                db.add(contact)
                db.flush()
                organization.contact_id = contact.id

            # Create address if needed
            if address_data:
                address = Address(**address_data.dict(exclude_unset=True))
                db.add(address)
                db.flush()
                organization.address_id = address.id

            db.add(organization)
            db.flush()
            award.organization_id = organization.id

    # 3. Appeals body, contact, and address
    if "appeals_body" in extracted_data:
        appeals_data = extracted_data["appeals_body"].dict(exclude_unset=True)
        contact_data = None
        address_data = None

        if "contact" in appeals_data:
            contact_data = appeals_data.pop("contact")

        if "address" in appeals_data:
            address_data = appeals_data.pop("address")

        # Update or create appeals body
        if award.appeals_body_id:
            # Update existing appeals body
            appeals_body = (
                db.query(AppealsBody)
                .filter(AppealsBody.id == award.appeals_body_id)
                .first()
            )

            # Update fields
            for key, value in appeals_data.items():
                setattr(appeals_body, key, value)

            # Update contact
            if contact_data and appeals_body.contact_id:
                contact = (
                    db.query(AppealsBodyContact)
                    .filter(AppealsBodyContact.id == appeals_body.contact_id)
                    .first()
                )
                for key, value in contact_data.dict(exclude_unset=True).items():
                    setattr(contact, key, value)
            elif contact_data:
                # Create new contact
                contact = AppealsBodyContact(**contact_data.dict(exclude_unset=True))
                db.add(contact)
                db.flush()
                appeals_body.contact_id = contact.id

            # Update address
            if address_data and appeals_body.address_id:
                address = (
                    db.query(Address)
                    .filter(Address.id == appeals_body.address_id)
                    .first()
                )
                for key, value in address_data.dict(exclude_unset=True).items():
                    setattr(address, key, value)
            elif address_data:
                # Create new address
                address = Address(**address_data.dict(exclude_unset=True))
                db.add(address)
                db.flush()
                appeals_body.address_id = address.id
        else:
            # Create new appeals body
            appeals_body = AppealsBody(**appeals_data)

            # Create contact if needed
            if contact_data:
                contact = AppealsBodyContact(**contact_data.dict(exclude_unset=True))
                db.add(contact)
                db.flush()
                appeals_body.contact_id = contact.id

            # Create address if needed
            if address_data:
                address = Address(**address_data.dict(exclude_unset=True))
                db.add(address)
                db.flush()
                appeals_body.address_id = address.id

            db.add(appeals_body)
            db.flush()
            award.appeals_body_id = appeals_body.id

    # 4. Update award record
    if "award_data" in extracted_data:
        for key, value in extracted_data["award_data"].items():
            setattr(award, key, value)

    # Update XML content
    award.xml_content = xml_content

    # 5. Update suppliers
    if "suppliers" in extracted_data and extracted_data["suppliers"]:
        # Remove existing suppliers
        for supplier in award.suppliers:
            db.delete(supplier)
        db.flush()

        # Create new suppliers
        for supplier_data in extracted_data["suppliers"]:
            supplier_dict = supplier_data.dict(exclude_unset=True)

            # Extract address data if present
            address_id = None
            if "address" in supplier_dict:
                address_data = supplier_dict.pop("address")
                address = Address(**address_data.dict(exclude_unset=True))
                db.add(address)
                db.flush()
                address_id = address.id

            # Create supplier
            supplier = AwardSupplier(award_id=award.id, **supplier_dict)
            if address_id:
                supplier.address_id = address_id

            db.add(supplier)

    db.commit()
    return award
