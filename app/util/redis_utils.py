import base64
import logging
from io import BytesIO
from typing import Dict, List, Union

from app.config.settings import settings
from app.util.zip import unzip




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



def normalize_filename(file_obj: BytesIO, filename: str) -> BytesIO:
    """
    Normalize a file object with a proper filename.
    Returns the normalized BytesIO object.
    """
    # Save current position
    current_pos = file_obj.tell()
    # Reset file position
    file_obj.seek(0)
    # Get content
    content = file_obj.read()
    # Create new BytesIO with the content
    byte_io = BytesIO(content)
    
    # Set name with lowercase extension
    if "." in filename:
        name_parts = filename.rsplit(".", 1)
        byte_io.name = f"{name_parts[0]}.{name_parts[1].lower()}"
    else:
        byte_io.name = filename
    
    # Restore original file position
    file_obj.seek(current_pos)
    
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
