from typing import List

from pydantic import BaseModel


class Sector(BaseModel):
    codes: List[str] = [""]


class Construction(BaseModel):
    codes: List[str] = [""]


class Handyman(Construction):
    codes = Construction.codes + [""]


class InformationTechnology(BaseModel):
    codes: List[str] = [""]


class Finance(BaseModel):
    codes: List[str] = [""]
