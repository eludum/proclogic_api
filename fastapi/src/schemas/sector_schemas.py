from typing import List, Optional

from pydantic import BaseModel


class Sector(BaseModel):
    id: int
    description: Optional[str]
    codes: List[str] = [""]


class Construction(Sector):
    codes: List[str] = [""]


class Handyman(Construction):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.codes.append([""])



class InformationTechnology(Sector):
    codes: List[str] = [""]


class Finance(Sector):
    codes: List[str] = [""]
