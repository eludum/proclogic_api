"""Read award details out of a PDF the user uploaded.

Nothing here writes to the database. The endpoint hands the result back for the
user to check and correct, because a model reading a scanned award notice
misreads amounts and dates often enough that silently persisting its output
would put wrong figures in front of a customer as if they were facts.

The file goes to OpenAI so the model can read scans as well as text PDFs, and is
deleted again as soon as the answer comes back -- it is a customer document and
has no reason to sit in the account afterwards.
"""

import base64
import logging
from typing import Optional, Tuple

from openai import AsyncOpenAI

from app.ai.recommend import handle_json_response_formats
from app.config.settings import settings
from app.schemas.company_award_schemas import ExtractedAward

logger = logging.getLogger(__name__)

# Award notices are a few pages. The cap is here so an accidental 200 MB upload
# is refused at the door rather than after being read into memory and shipped to
# OpenAI.
MAX_DOCUMENT_BYTES = 15 * 1024 * 1024

ALLOWED_CONTENT_TYPES = {"application/pdf"}

_PROMPT = """Je krijgt een gunningsdocument (award notice) van een Belgische \
overheidsopdracht. Het kan in het Nederlands, Frans, Duits of Engels zijn, en \
het kan een scan zijn.

Haal ALLEEN de volgende velden eruit, en alleen als ze echt in het document \
staan. Verzin niets: laat een veld op null staan als je het niet zeker weet.

- title: de opdrachtomschrijving / het voorwerp van de opdracht
- award_date: de gunningsdatum, als ISO 8601 (YYYY-MM-DD)
- winner: de naam van de gekozen inschrijver / opdrachtnemer
- buyer: de naam van de aanbestedende dienst
- value: het gegunde bedrag als getal, zonder valutateken en zonder \
duizendtalscheiding. Gebruik een punt als decimaalteken. Als er zowel een bedrag \
excl. als incl. btw staat, neem het bedrag EXCLUSIEF btw.
- currency: de ISO-valutacode van dat bedrag, bijvoorbeeld "EUR"
- reference_number: het besteknummer of de referentie van de opdracht
- notes: null, tenzij er iets staat dat de bovenstaande velden nodig heeft om \
juist gelezen te worden

Zet in "warnings" een korte lijst van velden waar je twijfelt, met de reden, \
bijvoorbeeld omdat de scan onduidelijk is of omdat er meerdere bedragen of \
percelen in het document staan. Wees hier eerlijk: dit wordt aan de gebruiker \
getoond zodat die net die velden nakijkt.

Antwoord met JSON in exact deze vorm:
{"title": null, "award_date": null, "winner": null, "buyer": null, \
"value": null, "currency": null, "reference_number": null, "notes": null, \
"warnings": []}"""


def validate_upload(filename: str, content_type: Optional[str], size: int) -> Optional[str]:
    """Return a rejection reason, or None when the upload is acceptable."""
    if size <= 0:
        return "Het bestand is leeg."
    if size > MAX_DOCUMENT_BYTES:
        return (
            f"Het bestand is te groot ({size / 1024 / 1024:.1f} MB). "
            f"Maximaal {MAX_DOCUMENT_BYTES // 1024 // 1024} MB."
        )
    looks_pdf = (content_type or "").split(";")[0].strip().lower() in ALLOWED_CONTENT_TYPES
    if not looks_pdf and not (filename or "").lower().endswith(".pdf"):
        return "Alleen PDF-bestanden worden ondersteund."
    return None


def _coerce(parsed: dict) -> Tuple[dict, list]:
    """Pull the known fields out of the model's JSON, dropping anything else.

    The model is asked for an exact shape but is not trusted to produce it, so
    unknown keys are ignored and a value that will not coerce becomes a warning
    rather than a 500.
    """
    warnings = []
    raw_warnings = parsed.get("warnings")
    if isinstance(raw_warnings, list):
        warnings = [str(w) for w in raw_warnings if w]

    fields: dict = {}
    for key in ("title", "winner", "buyer", "currency", "reference_number", "notes"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            fields[key] = value.strip()

    raw_value = parsed.get("value")
    if raw_value is not None:
        try:
            # Tolerate "1.240.000,00" and "1,240,000.00" alike: strip spaces and
            # currency marks, then decide which separator is decimal by position.
            if isinstance(raw_value, str):
                cleaned = raw_value.replace(" ", "").replace("€", "").replace("EUR", "")
                if "," in cleaned and "." in cleaned:
                    if cleaned.rfind(",") > cleaned.rfind("."):
                        cleaned = cleaned.replace(".", "").replace(",", ".")
                    else:
                        cleaned = cleaned.replace(",", "")
                elif "," in cleaned:
                    cleaned = cleaned.replace(",", ".")
                raw_value = cleaned
            fields["value"] = float(raw_value)
        except (TypeError, ValueError):
            warnings.append(f"Bedrag niet leesbaar: {parsed.get('value')!r}")

    raw_date = parsed.get("award_date")
    if raw_date:
        from datetime import datetime

        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                fields["award_date"] = datetime.strptime(str(raw_date)[:19], fmt)
                break
            except ValueError:
                continue
        else:
            warnings.append(f"Gunningsdatum niet leesbaar: {raw_date!r}")

    return fields, warnings


async def extract_award_from_pdf(
    client: AsyncOpenAI, filename: str, content: bytes
) -> ExtractedAward:
    """Ask the model to read an award notice. Never raises for a bad document."""
    file_id = None
    try:
        upload = await client.files.create(
            file=(filename or "document.pdf", content, "application/pdf"),
            purpose="user_data",
        )
        file_id = upload.id

        response = await client.chat.completions.create(
            model=settings.openai_model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "file", "file": {"file_id": file_id}},
                        {"type": "text", "text": _PROMPT},
                    ],
                }
            ],
        )
        parsed = handle_json_response_formats(response.choices[0].message.content or "")
        if not isinstance(parsed, dict):
            raise ValueError(f"expected a JSON object, got {type(parsed).__name__}")

        fields, warnings = _coerce(parsed)
        return ExtractedAward(
            **fields, warnings=warnings, source_document_name=filename
        )
    except Exception as exc:
        logger.error("Award extraction failed for %r: %s", filename, exc, exc_info=exc)
        return ExtractedAward(
            warnings=[
                "Het document kon niet automatisch gelezen worden. "
                "Vul de gegevens hieronder handmatig in."
            ],
            source_document_name=filename,
        )
    finally:
        if file_id:
            # Customer document; there is no reason for it to outlive the request.
            try:
                await client.files.delete(file_id)
            except Exception as exc:
                logger.warning("Could not delete uploaded file %s: %s", file_id, exc)


def encode_inline(content: bytes) -> str:
    """Base64 for the inline-data form, kept for callers that cannot upload."""
    return base64.b64encode(content).decode("ascii")
