from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from config.postgres import get_session

from models.publication_models import Company, Sector
from schemas.publication_schemas import CompanySchema, SectorSchema


async def create_company(company_data: CompanySchema) -> CompanySchema:
    """
    Create a new company in the database.

    Args:
        company_data (CompanySchema): The data to create a company.
        session (Optional[AsyncSession]): Optional database session.

    Returns:
        CompanySchema: The newly created company as a Pydantic schema.
    """
    async with get_session() as session:
        try:
            # Create or fetch related sectors
            sectors = []
            for sector_data in company_data.interessed_sectors:
                sector = await session.execute(
                    select(Sector).where(Sector.name == sector_data.name)
                )
                existing_sector = sector.scalars().first()
                if existing_sector:
                    sectors.append(existing_sector)
                else:
                    new_sector = Sector(name=sector_data.name, codes=sector_data.codes)
                    session.add(new_sector)
                    await session.flush()
                    sectors.append(new_sector)

            # Create the company
            new_company = Company(
                vat_number=company_data.vat_number,
                name=company_data.name,
                summary_activities=company_data.summary_activities,
                interessed_sectors=sectors,
            )
            session.add(new_company)
            await session.commit()

            return CompanySchema.model_validate(new_company)
        except IntegrityError:
            await session.rollback()
            raise ValueError("A company with this VAT number already exists.")
        except Exception as e:
            await session.rollback()
            raise e


async def update_company(vat_number: str, company_data: CompanySchema) -> CompanySchema:
    """
    Update an existing company in the database.

    Args:
        vat_number (str): The VAT number of the company to update.
        company_data (CompanySchema): The updated data for the company.
        session (Optional[AsyncSession]): Optional database session.

    Returns:
        CompanySchema: The updated company as a Pydantic schema.
    """
    async with get_session() as session:
        try:
            result = await session.execute(
                select(Company).where(Company.vat_number == vat_number)
            )
            company = result.scalars().first()

            if not company:
                raise ValueError("Company not found.")

            # Update fields
            company.name = company_data.name
            company.summary_activities = company_data.summary_activities

            # Update related sectors
            updated_sectors = []
            for sector_data in company_data.interessed_sectors:
                sector = await session.execute(
                    select(Sector).where(Sector.name == sector_data.name)
                )
                existing_sector = sector.scalars().first()
                if existing_sector:
                    updated_sectors.append(existing_sector)
                else:
                    new_sector = Sector(name=sector_data.name, codes=sector_data.codes)
                    session.add(new_sector)
                    await session.flush()
                    updated_sectors.append(new_sector)

            company.interessed_sectors = updated_sectors

            await session.commit()

            return CompanySchema.model_validate(company)
        except Exception as e:
            await session.rollback()
            raise e


async def delete_company(vat_number: str) -> bool:
    """
    Delete a company from the database.

    Args:
        vat_number (str): The VAT number of the company to delete.
        session (Optional[AsyncSession]): Optional database session.

    Returns:
        bool: True if the company was deleted, False otherwise.
    """
    async with get_session() as session:
        try:
            result = await session.execute(
                select(Company).where(Company.vat_number == vat_number)
            )
            company = result.scalars().first()

            if not company:
                raise ValueError("Company not found.")

            await session.delete(company)
            await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            raise e


async def create_sector(sector_data: SectorSchema) -> SectorSchema:
    """
    Create a new sector.

    Args:
        sector_data (SectorSchema): The data for the new sector.
        session (Optional[AsyncSession]): Optional database session.

    Returns:
        SectorSchema: The newly created sector as a Pydantic schema.
    """
    async with get_session() as session:
        try:
            new_sector = Sector(name=sector_data.name, codes=sector_data.codes)
            session.add(new_sector)
            await session.commit()

            return SectorSchema.model_validate(new_sector)
        except IntegrityError as e:
            await session.rollback()
            raise ValueError(f"Error creating sector: {str(e)}")


async def update_sector(sector_id: int, sector_data: SectorSchema) -> SectorSchema:
    """
    Update an existing sector.

    Args:
        sector_id (int): The ID of the sector to update.
        sector_data (SectorSchema): The new data for the sector.
        session (Optional[AsyncSession]): Optional database session.

    Returns:
        SectorSchema: The updated sector as a Pydantic schema.
    """
    async with get_session() as session:
        try:
            result = await session.execute(select(Sector).where(Sector.id == sector_id))
            sector = result.scalars().first()

            if not sector:
                raise ValueError("Sector not found.")

            # Update fields
            sector.name = sector_data.name
            sector.codes = sector_data.codes

            await session.commit()

            return SectorSchema.model_validate(sector)
        except Exception as e:
            await session.rollback()
            raise e


async def delete_sector(sector_id: int) -> bool:
    """
    Delete a sector by ID.

    Args:
        sector_id (int): The ID of the sector to delete.
        session (Optional[AsyncSession]): Optional database session.

    Returns:
        bool: True if the sector was deleted, False otherwise.
    """
    async with get_session() as session:
        try:
            result = await session.execute(select(Sector).where(Sector.id == sector_id))
            sector = result.scalars().first()

            if not sector:
                raise ValueError("Sector not found.")

            await session.delete(sector)
            await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            raise e
