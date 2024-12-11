from typing import Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl


class Link(BaseModel):
    xml: Dict[str, HttpUrl]
    pdf: Dict[str, HttpUrl]
    pdfs: Dict[str, HttpUrl]
    html: Dict[str, HttpUrl]
    htmlDirect: Dict[str, HttpUrl]


class NoticeTitle(BaseModel):
    hun: str
    lav: str
    swe: str
    gle: str
    ell: str
    spa: str
    est: str
    nld: str
    fin: str
    pol: str
    hrv: str
    ces: str
    dan: str
    ron: str
    por: str
    slk: str
    fra: str
    mlt: str
    deu: str
    lit: str
    ita: str
    bul: str
    slv: str
    eng: str


class Notice(BaseModel):
    document_url_lot: Optional[List[HttpUrl]] = Field(
        None, alias='document-url-lot')
    procedure_type: Optional[str] = Field(
        None, alias='procedure-type')
    classification_cpv: Optional[List[str]] = Field(
        None, alias='classification-cpv')
    publication_number: Optional[str] = Field(
        None, alias='publication-number')
    contract_nature: Optional[List[str]] = Field(
        None, alias='contract-nature')
    publication_date: Optional[str] = Field(
        None, alias='publication-date')
    links: Link
    notice_title: Optional[NoticeTitle] = Field(
        None, alias='notice-title')
    tender_value_cur: Optional[List[str]] = Field(
        None, alias='tender-value-cur')
    tender_value: Optional[List[str]] = Field(
        None, alias='tender-value')
    organisation_contact_point_tenderer: Optional[List[str]] = Field(
        None, alias='organisation-contact-point-tenderer')


class Ted(BaseModel):
    notices: List[Notice]
    totalNoticeCount: int
    iterationNextToken: Optional[str] = None
