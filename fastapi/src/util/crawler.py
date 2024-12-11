import httpx
from pydantic import BaseModel


class NoticeCrawler(BaseModel):
    id: int
    title: str


class TedNoticeCrawler(NoticeCrawler):
    json: str

    async def crawl(self) -> None:
        for notice in self.json:
            r = httpx.get(notice["document-url-lot"][0])
            # TODO: store in redis
            # TODO: rag
