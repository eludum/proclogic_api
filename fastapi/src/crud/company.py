from typing import List, Optional

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config.postgres import get_db_session
from models.company_models import Company, Sector
from schemas.company_schemas import CompanySchema, SectorSchema


async def get_all_companies(db: Optional[AsyncSession] = None) -> List[CompanySchema]:
    """
    Fetch all companies from the database and return them as a list of Pydantic schemas.
    """
    db = db or await get_db_session()

    async with db:
        try:
            # Query all companies
            result = await db.execute(select(Company).options())
            companies = result.scalars().all()

            # Convert SQLAlchemy objects to Pydantic schemas
            return [CompanySchema.model_validate(company) for company in companies]
        except SQLAlchemyError as e:
            print(f"Database error: {e}")
            raise


async def create_company(company_data: CompanySchema, db: Optional[AsyncSession] = None) -> CompanySchema:
    """
    Create a new company in the database.

    Args:
        company_data (CompanySchema): The data to create a company.
        db (Optional[AsyncSession]): Optional database session.

    Returns:
        CompanySchema: The newly created company as a Pydantic schema.
    """
    db = db or await get_db_session()

    async with db:
        try:
            # Create or fetch related sectors
            sectors = []
            for sector_data in company_data.interessed_sectors:
                sector = await db.execute(
                    select(Sector).where(Sector.name == sector_data.name)
                )
                existing_sector = sector.scalars().first()
                if existing_sector:
                    sectors.append(existing_sector)
                else:
                    new_sector = Sector(name=sector_data.name, codes=sector_data.codes)
                    db.add(new_sector)
                    await db.flush()
                    sectors.append(new_sector)

            # Create the company
            new_company = Company(
                vat_number=company_data.vat_number,
                name=company_data.name,
                summary_activities=company_data.summary_activities,
                interessed_sectors=sectors,
            )
            db.add(new_company)
            await db.commit()
            await db.refresh(new_company)
            return CompanySchema.model_validate(new_company)
        except IntegrityError:
            await db.rollback()
            raise ValueError("A company with this VAT number already exists.")
        except Exception as e:
            await db.rollback()
            raise e


async def update_company(
    vat_number: str, company_data: CompanySchema, db: Optional[AsyncSession] = None
) -> CompanySchema:
    """
    Update an existing company in the database.

    Args:
        vat_number (str): The VAT number of the company to update.
        company_data (CompanySchema): The updated data for the company.
        db (Optional[AsyncSession]): Optional database session.

    Returns:
        CompanySchema: The updated company as a Pydantic schema.
    """
    db = db or await get_db_session()

    async with db:
        try:
            result = await db.execute(select(Company).where(Company.vat_number == vat_number))
            company = result.scalars().first()

            if not company:
                raise ValueError("Company not found.")

            # Update fields
            company.name = company_data.name
            company.summary_activities = company_data.summary_activities

            # Update related sectors
            updated_sectors = []
            for sector_data in company_data.interessed_sectors:
                sector = await db.execute(
                    select(Sector).where(Sector.name == sector_data.name)
                )
                existing_sector = sector.scalars().first()
                if existing_sector:
                    updated_sectors.append(existing_sector)
                else:
                    new_sector = Sector(name=sector_data.name, codes=sector_data.codes)
                    db.add(new_sector)
                    await db.flush()
                    updated_sectors.append(new_sector)

            company.interessed_sectors = updated_sectors

            await db.commit()
            await db.refresh(company)
            return CompanySchema.model_validate(company)
        except Exception as e:
            await db.rollback()
            raise e


async def delete_company(vat_number: str, db: Optional[AsyncSession] = None) -> bool:
    """
    Delete a company from the database.

    Args:
        vat_number (str): The VAT number of the company to delete.
        db (Optional[AsyncSession]): Optional database session.

    Returns:
        bool: True if the company was deleted, False otherwise.
    """
    db = db or await get_db_session()

    async with db:
        try:
            result = await db.execute(select(Company).where(Company.vat_number == vat_number))
            company = result.scalars().first()

            if not company:
                raise ValueError("Company not found.")

            await db.delete(company)
            await db.commit()
            return True
        except Exception as e:
            await db.rollback()
            raise e


async def create_sector(sector_data: SectorSchema, db: Optional[AsyncSession] = None) -> SectorSchema:
    """
    Create a new sector.

    Args:
        sector_data (SectorSchema): The data for the new sector.
        db (Optional[AsyncSession]): Optional database session.

    Returns:
        SectorSchema: The newly created sector as a Pydantic schema.
    """
    db = db or await get_db_session()

    async with db:
        try:
            new_sector = Sector(name=sector_data.name, codes=sector_data.codes)
            db.add(new_sector)
            await db.commit()
            await db.refresh(new_sector)
            return SectorSchema.model_validate(new_sector)
        except IntegrityError as e:
            await db.rollback()
            raise ValueError(f"Error creating sector: {str(e)}")


async def update_sector(sector_id: int, sector_data: SectorSchema, db: Optional[AsyncSession] = None) -> SectorSchema:
    """
    Update an existing sector.

    Args:
        sector_id (int): The ID of the sector to update.
        sector_data (SectorSchema): The new data for the sector.
        db (Optional[AsyncSession]): Optional database session.

    Returns:
        SectorSchema: The updated sector as a Pydantic schema.
    """
    db = db or await get_db_session()

    async with db:
        try:
            result = await db.execute(select(Sector).where(Sector.id == sector_id))
            sector = result.scalars().first()

            if not sector:
                raise ValueError("Sector not found.")

            # Update fields
            sector.name = sector_data.name
            sector.codes = sector_data.codes

            await db.commit()
            await db.refresh(sector)

            return SectorSchema.model_validate(sector)
        except Exception as e:
            await db.rollback()
            raise e


async def delete_sector(sector_id: int, db: Optional[AsyncSession] = None) -> bool:
    """
    Delete a sector by ID.

    Args:
        sector_id (int): The ID of the sector to delete.
        db (Optional[AsyncSession]): Optional database session.

    Returns:
        bool: True if the sector was deleted, False otherwise.
    """
    db = db or await get_db_session()

    async with db:
        try:
            result = await db.execute(select(Sector).where(Sector.id == sector_id))
            sector = result.scalars().first()

            if not sector:
                raise ValueError("Sector not found.")

            await db.delete(sector)
            await db.commit()
            return True
        except Exception as e:
            await db.rollback()
            raise e
