from typing import List

from pydantic import BaseModel


class Crawler(BaseModel):
    ids: List[str]


class PubProcPublicationCrawler(Crawler):
    # TODO: easiest would be to use selenium or playwirght?
    pass
