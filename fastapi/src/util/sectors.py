from pydantic import BaseModel
from typing import List


class Sector(BaseModel):
    codes: List[str] = [""]

class Construction(BaseModel):
    codes: List[str] = [""]


class InformationTechnology(BaseModel):
    codes: List[str] = [""]


class Finance(BaseModel):
    codes: List[str] = [""]
