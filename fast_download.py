import os
import sys
import asyncio
import math
from telethon import TelegramClient
from telethon.tl.functions.upload import GetFileRequest
from telethon.tl.types import InputDocumentFileLocation

CHUNK_SIZE = 512 * 1024  # 512KB per request chunk

async def download_part(client, location, offset, size, file_path, progress_cb, downloaded_tracker, total_size):
    dc_id = location.dc_id
    # Get or create raw sender connection for DC
    sender = await client._borrow_upload_connection(dc_id)
    try:
        current_offset = offset
        end_offset = offset + size
        with open(file_path, "r+b") as f:
            while current_offset < end_offset:
                request_size = min(CHUNK_SIZE, end_offset - current_offset)
                result = await sender(GetFileRequest(
                    location=location,
                    offset=current_offset,
                    limit=request_size,
                    precise=True,
                    cdn_supported=False
                ))
                if not result.bytes:
                    break
                f.seek(current_offset)
                f.write(result.bytes)
                current_offset += len(result.bytes)
                downloaded_tracker[0] += len(result.bytes)
                if progress_cb:
                    progress_cb(downloaded_tracker[0], total_size)
    finally:
        await client._return_upload_connection(dc_id, sender)

async def fast_download_media(client, msg, target_path, progress_callback=None, parallel_connections=8):
    """
    High-Speed Telethon Downloader using Direct Data-Center Upload Connections.
    Achieves maximum network saturation without single-connection throttling.
    """
    if not msg.media or not hasattr(msg.media, 'document'):
        await msg.download_media(file=target_path, progress_callback=progress_callback)
        return

    doc = msg.media.document
    total_size = doc.size
    
    # Initialize zeroed output file
    with open(target_path, "wb") as f:
        f.truncate(total_size)

    location = InputDocumentFileLocation(
        id=doc.id,
        access_hash=doc.access_hash,
        file_reference=doc.file_reference,
        thumb_size=""
    )

    part_size = math.ceil(total_size / parallel_connections)
    downloaded_tracker = [0]
    tasks = []

    for i in range(parallel_connections):
        offset = i * part_size
        size = min(part_size, total_size - offset)
        if size > 0:
            tasks.append(download_part(client, location, offset, size, target_path, progress_callback, downloaded_tracker, total_size))

    await asyncio.gather(*tasks)
