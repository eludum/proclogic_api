from typing import List, Tuple, Union

from schemas.pubproc_schemas import Publication
from schemas.ted_schemas import Notice
from pydantic import BaseModel
from schemas.sector_schemas import Sector


class ProcLogicPublication(BaseModel):
    id: str
    original_notice: Union[Publication, Notice]
    title: str
    description: str
    url: str
    start_date: str
    end_date: str
    sectors: List[Sector]
    recommended: Tuple[bool, str]
