import logging
import shutil
from os import path
from typing import IO, Dict
import zipfile

# Extracted members up to this size stay in RAM; anything larger spills to disk.
# Mirrors the download path's NamedSpooledFile threshold in redis_utils so a
# large tender's files never all sit in memory at once.
_MEMBER_SPILL_THRESHOLD = 2 * 1024 * 1024


def unzip(
    zip_file: IO[bytes], publication_workspace_id: str = "vector store"
) -> Dict[str, IO[bytes]]:
    """Extract a ZIP into a map of ``{basename: file object}``.

    ``zip_file`` is a seekable binary file object (e.g. the NamedSpooledFile a
    document was downloaded into). Each member is streamed out via
    ``ZipFile.open()`` + ``copyfileobj`` into its own disk-spilling
    NamedSpooledFile, so neither the archive nor its contents are held whole in
    RAM.

    The previous version took ``zip_bytes: bytes`` and did
    ``BytesIO(zip_bytes)`` + ``zip_file.read(name)`` per member — materializing
    the entire archive *and* every extracted file in memory. A single large
    tender ZIP spiked past the 8Gi limit and OOMKilled the scraper in a crash
    loop, undoing the streaming download fix upstream.
    """
    # Imported lazily to avoid a circular import: redis_utils imports unzip at
    # module load, before NamedSpooledFile is defined.
    from app.util.redis_utils import NamedSpooledFile

    file_map: Dict[str, IO[bytes]] = {}

    try:
        zip_file.seek(0)
        with zipfile.ZipFile(zip_file) as zf:
            for file_name in zf.namelist():
                # Get just the base filename without folder path
                base_file_name = path.basename(file_name)

                # Skip if it's a directory (empty base name)
                if not base_file_name:
                    continue

                spooled = NamedSpooledFile(max_size=_MEMBER_SPILL_THRESHOLD)
                with zf.open(file_name) as member:
                    shutil.copyfileobj(member, spooled)
                spooled.seek(0)
                spooled.name = base_file_name
                file_map[base_file_name] = spooled

            return file_map
    except zipfile.BadZipFile as e:
        logging.error(
            f"Invalid zip file received for {publication_workspace_id}: {str(e)}"
        )
        return {}
