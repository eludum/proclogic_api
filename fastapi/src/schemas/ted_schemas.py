from typing import Any, List, Optional
from pydantic import BaseModel, Field


class Xml(BaseModel):
    MUL: str


class Pdf(BaseModel):
    BUL: str
    SPA: str
    CES: str
    DAN: str
    DEU: str
    EST: str
    ELL: str
    ENG: str
    FRA: str
    GLE: str
    HRV: str
    ITA: str
    LAV: str
    LIT: str
    HUN: str
    MLT: str
    NLD: str
    POL: str
    POR: str
    RON: str
    SLK: str
    SLV: str
    FIN: str
    SWE: str


class Pdfs(BaseModel):
    DEU: Optional[str] = None
    ITA: Optional[str] = None
    POL: Optional[str] = None
    FRA: Optional[str] = None
    SPA: Optional[str] = None
    BUL: Optional[str] = None


class Html(BaseModel):
    BUL: str
    SPA: str
    CES: str
    DAN: str
    DEU: str
    EST: str
    ELL: str
    ENG: str
    FRA: str
    GLE: str
    HRV: str
    ITA: str
    LAV: str
    LIT: str
    HUN: str
    MLT: str
    NLD: str
    POL: str
    POR: str
    RON: str
    SLK: str
    SLV: str
    FIN: str
    SWE: str


class HtmlDirect(BaseModel):
    BUL: str
    SPA: str
    CES: str
    DAN: str
    DEU: str
    EST: str
    ELL: str
    ENG: str
    FRA: str
    GLE: str
    HRV: str
    ITA: str
    LAV: str
    LIT: str
    HUN: str
    MLT: str
    NLD: str
    POL: str
    POR: str
    RON: str
    SLK: str
    SLV: str
    FIN: str
    SWE: str


class Links(BaseModel):
    xml: Xml
    pdf: Pdf
    pdfs: Pdfs
    html: Html
    htmlDirect: HtmlDirect


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
    document_url_lot: Optional[List[str]] = Field(
        None, alias='document-url-lot')
    procedure_type: str = Field(..., alias='procedure-type')
    classification_cpv: List[str] = Field(..., alias='classification-cpv')
    publication_number: str = Field(..., alias='publication-number')
    contract_nature: List[str] = Field(..., alias='contract-nature')
    publication_date: str = Field(..., alias='publication-date')
    links: Links
    notice_title: NoticeTitle = Field(..., alias='notice-title')
    tender_value_cur: Optional[List[str]] = Field(
        None, alias='tender-value-cur')
    tender_value: Optional[List[str]] = Field(None, alias='tender-value')
    organisation_contact_point_tenderer: Optional[List[str]] = Field(
        None, alias='organisation-contact-point-tenderer'
    )


class Ted(BaseModel):
    notices: List[Notice]
    totalNoticeCount: int
    iterationNextToken: Any
