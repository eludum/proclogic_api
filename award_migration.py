# app/util/award_migration.py
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.publication_models import Publication
from app.models.award_models import Award, AwardSupplier
from app.util.award_parser import extract_award_data_from_xml, extract_suppliers_from_award_data
from app.config.postgres import get_session


def migrate_pickle_awards_to_models(batch_size: int = 100) -> int:
    """
    Migrate pickle awards to structured models.
    Returns the number of migrated records.
    """
    total_migrated = 0
    
    with get_session() as session:
        # Count total records to migrate
        total_count = session.query(Publication).filter(
            Publication.award.isnot(None)
        ).count()
        
        logging.info(f"Found {total_count} publications with award data to migrate")
        
        # TODO: alembic migration too

        offset = 0
        while offset < total_count:
            # Get batch of publications with pickle awards
            publications = session.query(Publication).filter(
                Publication.award.isnot(None)
            ).offset(offset).limit(batch_size).all()
            
            if not publications:
                break
                
            batch_count = 0
            for publication in publications:
                try:
                    # Skip if already migrated
                    if hasattr(publication, 'award_data') and publication.award_data is not None:
                        continue
                        
                    # Get pickle award data
                    pickle_award = publication.award
                    
                    # Create award model
                    award = Award(
                        publication_workspace_id=publication.publication_workspace_id,
                        winner_name=pickle_award.get("winner"),
                        award_value=pickle_award.get("value", 0),
                    )
                    
                    # Extract any XML content if available
                    xml_content = None
                    for notice_id in publication.notice_ids:
                        # Try to get XML content for this notice
                        # This is hypothetical - you'll need to implement how to get the XML  
                        xml_content = get_notice_xml(notice_id)
                        if xml_content:
                            break
                    
                    if xml_content:
                        award.xml_content = xml_content
                        
                        # Extract more detailed data from XML
                        award_data = extract_award_data_from_xml(xml_content)
                        
                        # Update award with extracted data
                        for key, value in award_data.items():
                            if key != "suppliers" and hasattr(award, key):
                                setattr(award, key, value)
                    
                    # Add suppliers
                    suppliers = []
                    if "suppliers" in pickle_award and isinstance(pickle_award["suppliers"], list):
                        for supplier_data in pickle_award["suppliers"]:
                            supplier = AwardSupplier(
                                name=supplier_data.get("name", "Unknown"),
                                vat_number=supplier_data.get("id"),
                            )
                            suppliers.append(supplier)
                    
                    # If we have XML data but no suppliers from pickle, extract from XML
                    if not suppliers and xml_content:
                        suppliers_data = extract_suppliers_from_award_data(
                            extract_award_data_from_xml(xml_content)
                        )
                        for supplier_data in suppliers_data:
                            supplier = AwardSupplier(
                                name=supplier_data.get("name", "Unknown"),
                                vat_number=supplier_data.get("vat_number"),
                                email=supplier_data.get("email"),
                                website=supplier_data.get("website"),
                            )
                            suppliers.append(supplier)
                    
                    award.suppliers = suppliers
                    
                    # Add to session
                    session.add(award)
                    batch_count += 1
                    
                except Exception as e:
                    logging.error(f"Error migrating award for publication {publication.publication_workspace_id}: {e}")
            
            # Commit batch
            if batch_count > 0:
                session.commit()
                total_migrated += batch_count
                logging.info(f"Migrated {total_migrated}/{total_count} awards")
            
            offset += batch_size
    
    return total_migrated
