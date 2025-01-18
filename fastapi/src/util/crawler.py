import httpx
from pydantic import BaseModel


class Crawler(BaseModel):
    id: int
    title: str


class TedNoticeCrawler(Crawler):
    json: str

    async def crawl(self) -> None:
        for notice in self.json:
            r = httpx.get(notice["document-url-lot"][0])
            # TODO: store in redis
            # TODO: rag


class PubProcPublicationCrawler(Crawler):
    # easiest would be to use selenium or playwirght?
    pass
