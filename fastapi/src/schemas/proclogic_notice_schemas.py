from typing import List, Tuple, Union

from models.pubproc_models import Publication
from models.ted_models import Notice
from pydantic import BaseModel
from schemas.sector_schemas import Sector


class ProcLogicNotice(BaseModel):
    id: str
    original_notice: Union[Publication, Notice]
    title: str
    description: str
    url: str
    start_date: str
    end_date: str
    sectors: List[Sector]
    recommended: Tuple[bool, str]
