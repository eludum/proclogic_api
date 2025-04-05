from io import BytesIO
import logging
from os import path
from typing import Dict
import zipfile


def unzip(
    zip_bytes: bytes, publication_workspace_id: str = "vector store"
) -> Dict[str, BytesIO]:
    file_map = {}

    try:
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zip_file:
            for file_name in zip_file.namelist():
                file_content = zip_file.read(file_name)

                # Get just the base filename without folder path
                base_file_name = path.basename(file_name)

                # Skip if it's a directory (empty base name)
                if not base_file_name:
                    continue

                # Regular file, not a zip
                file_data = BytesIO(file_content)
                file_data.name = base_file_name
                file_map[base_file_name] = file_data

            return file_map
    except zipfile.BadZipFile as e:
        logging.error(
            f"Invalid zip file received for {publication_workspace_id}: {str(e)}"
        )
        return {}
