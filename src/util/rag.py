# TODO: https://cookbook.openai.com/examples/parse_pdf_docs_for_rag

from pydantic import BaseModel

class Vectorizer(BaseModel):
    title: str
    text: str

