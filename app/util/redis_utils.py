import base64
import logging
import tempfile
from io import BytesIO
from typing import Dict, List, Union

from app.config.settings import settings
from app.util.zip import unzip


class NamedSpooledFile(tempfile.SpooledTemporaryFile):
    """A SpooledTemporaryFile that carries a settable ``.name`` so it's a drop-in
    for ``BytesIO`` everywhere we pass documents around.

    Small files stay in RAM; anything past ``max_size`` spills to disk. Document
    downloads use this so a publication's files don't all sit in memory at once —
    that's what OOMKilled the scraper.
    """

    @property
    def name(self):
        return getattr(self, "_doc_name", None)

    @name.setter
    def name(self, value):
        self._doc_name = value


def encode_file_to_base64(file_obj: Union[BytesIO, bytes]) -> str:
    """
    Convert a file object or bytes to a base64 encoded string.
    """
    try:
        # If it's a file-like object
        if hasattr(file_obj, "read") and callable(file_obj.read):
            # Save current position
            current_pos = file_obj.tell()
            # Read all content
            file_obj.seek(0)
            content = file_obj.read()
            # Restore position
            file_obj.seek(current_pos)
        else:
            # It's already bytes
            content = file_obj

        # Convert to base64
        return base64.b64encode(content).decode("utf-8")
    except Exception as e:
        logging.error(f"Error encoding file to base64: {e}")
        raise


def read_file_bytes(file_obj: Union[BytesIO, bytes]) -> bytes:
    """
    Read the raw bytes from a file-like object (or pass through bytes), restoring
    the stream position so the caller can still read the object afterwards.

    Used by the document cache to store raw bytes instead of base64 — base64
    inflates payloads by ~33%, which is exactly what bloated Redis.
    """
    if hasattr(file_obj, "read") and callable(file_obj.read):
        current_pos = file_obj.tell()
        file_obj.seek(0)
        content = file_obj.read()
        file_obj.seek(current_pos)
        return content
    return file_obj


def decode_base64_to_bytesio(base64_str: str, filename: str = None) -> BytesIO:
    """
    Convert a base64 encoded string to a BytesIO object.
    """
    try:
        # Decode the base64 string
        binary_data = base64.b64decode(base64_str)

        # Create a BytesIO object
        file_obj = BytesIO(binary_data)

        # Set filename if provided
        if filename:
            file_obj.name = filename

        return file_obj
    except Exception as e:
        logging.error(f"Error decoding base64 to file: {e}")


def normalize_filename(file_obj, filename: str):
    """
    Give a file object a normalized name (lowercase extension) and rewind it,
    WITHOUT copying its contents into memory (the old version did a full
    ``BytesIO(file_obj.read())`` copy per file, which blew up memory for large
    document sets). Returns the same object with ``.name`` set.
    """
    if "." in filename:
        base, ext = filename.rsplit(".", 1)
        norm = f"{base}.{ext.lower()}"
    else:
        norm = filename

    try:
        file_obj.seek(0)
        file_obj.name = norm
        return file_obj
    except Exception:
        # Fallback only if .name can't be set on this object (shouldn't happen
        # for BytesIO / NamedSpooledFile).
        file_obj.seek(0)
        byte_io = BytesIO(file_obj.read())
        byte_io.name = norm
        return byte_io


def is_file_allowed_for_assistant_file_search(
    filename: str, accepted_formats: List[str] = None
) -> bool:
    if accepted_formats is None:
        accepted_formats = [
            fmt.lstrip(".").lower()
            for fmt in settings.openai_vector_store_accepted_formats
        ]

    # Extract the extension in lowercase for comparison
    file_extension = ""
    if "." in filename:
        file_extension = filename.split(".")[-1].lower()

    # Skip if extension not in accepted formats
    return file_extension in accepted_formats


def prepare_files_for_vector_store(filesmap: Dict[str, BytesIO]) -> List[BytesIO]:
    """
    Process files for uploading to OpenAI vector store.

    Args:
        filesmap: Dictionary mapping filenames to BytesIO objects
        accepted_formats: List of accepted file extensions (without dots), uses settings if None

    Returns:
        List of BytesIO objects ready for upload to vector store
    """

    file_objects = []

    for file_name, file_data in filesmap.items():
        try:
            # Extract the extension in lowercase for comparison
            if is_file_allowed_for_assistant_file_search(filename=file_name):
                file_objects.append(
                    normalize_filename(file_obj=file_data, filename=file_name)
                )
                continue

            if ".zip" in file_name:
                file_data.seek(0)

                unzipped_files = unzip(
                    zip_bytes=file_data.read(), publication_workspace_id="filename"
                )

                for filename_unzipped, file_data_unzipped in unzipped_files.items():
                    if is_file_allowed_for_assistant_file_search(
                        filename=filename_unzipped
                    ):
                        file_objects.append(
                            normalize_filename(
                                file_obj=file_data_unzipped, filename=filename_unzipped
                            )
                        )

        except Exception as e:
            logging.error(f"Error processing file {file_name}: {e}")
            continue

    return file_objects
