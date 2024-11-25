from pydantic import BaseModel
from typing import List


class Sector(BaseModel):
    codes_pubproc: List[str]
    codes_ted: List[str]


class Construction(Sector):
    codes: List[str] = [""]


class InformationTechnology(Sector):
    codes: List[str] = [""]


class Finance(Sector):
    codes: List[str] = [""]
