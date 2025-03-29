import base64
from io import BytesIO
import logging
from typing import Union


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


def decode_base64_to_bytesio(base64_str: str, filename: str = None) -> io.BytesIO:
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
        raise


import logging
from io import BytesIO
from typing import Dict, List, Any

from app.config.settings import Settings

settings = Settings()


def prepare_files_for_vector_store(
    filesmap: Dict[str, BytesIO], accepted_formats: List[str] = None
) -> List[BytesIO]:
    """
    Process files for uploading to OpenAI vector store.

    Args:
        filesmap: Dictionary mapping filenames to BytesIO objects
        accepted_formats: List of accepted file extensions (without dots), uses settings if None

    Returns:
        List of BytesIO objects ready for upload to vector store
    """
    if accepted_formats is None:
        accepted_formats = [
            fmt.lstrip(".").lower()
            for fmt in settings.openai_vector_store_accepted_formats
        ]

    file_objects = []

    for filename, file_obj in filesmap.items():
        try:
            # Extract the extension in lowercase for comparison
            file_extension = ""
            if "." in filename:
                file_extension = filename.split(".")[-1].lower()

            # Skip if extension not in accepted formats
            if file_extension not in accepted_formats:
                continue

            # Create a new BytesIO with the content
            file_obj.seek(0)
            content = file_obj.read()
            byte_io = BytesIO(content)

            # Set name with lowercase extension
            if "." in filename:
                name_parts = filename.rsplit(".", 1)
                byte_io.name = f"{name_parts[0]}.{name_parts[1].lower()}"
            else:
                byte_io.name = filename

            file_objects.append(byte_io)

        except Exception as e:
            logging.error(f"Error processing file {filename}: {e}")
            continue

    return file_objects
