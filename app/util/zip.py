import logging
import shutil
import tempfile
from os import path
from typing import IO, Dict
import zipfile

# Extracted members up to this size stay in RAM; anything larger spills to disk.
# Mirrors the download path's NamedSpooledFile threshold in redis_utils so a
# large tender's files never all sit in memory at once.
_MEMBER_SPILL_THRESHOLD = 2 * 1024 * 1024

# Extraction spills members to the tempdir, which in a container is the shared
# overlay/host disk — other workloads on the node write there too. So bound how
# much one archive may write: keep the spill filesystem above _MIN_FREE_DISK and
# never extract more than _MAX_ARCHIVE_UNCOMPRESSED (keep this under whatever
# ephemeral-storage limit the deployment sets, so the runtime never evicts us).
# ZIP central-directory sizes let us decide before writing a single byte.
_MIN_FREE_DISK = 4 * 1024 * 1024 * 1024
_MAX_ARCHIVE_UNCOMPRESSED = 6 * 1024 * 1024 * 1024
_MiB = 1024 * 1024


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
            # Pre-flight: refuse an archive that wouldn't fit on disk with room
            # to spare, BEFORE writing anything. Central-directory file_size is
            # the uncompressed size, so this needs no decompression.
            declared_total = sum(info.file_size for info in zf.infolist())
            free = shutil.disk_usage(tempfile.gettempdir()).free
            budget = min(free - _MIN_FREE_DISK, _MAX_ARCHIVE_UNCOMPRESSED)
            if declared_total > budget:
                logging.error(
                    "Refusing to extract %s: %d MiB uncompressed exceeds the "
                    "%d MiB disk budget (free=%d MiB, reserve=%d MiB, cap=%d "
                    "MiB) — skipping to protect the node disk.",
                    publication_workspace_id,
                    declared_total // _MiB,
                    max(budget, 0) // _MiB,
                    free // _MiB,
                    _MIN_FREE_DISK // _MiB,
                    _MAX_ARCHIVE_UNCOMPRESSED // _MiB,
                )
                return {}

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
