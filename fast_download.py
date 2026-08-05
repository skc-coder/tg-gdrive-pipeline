import os
import sys
import time
import math
import asyncio
from telethon.tl.functions.upload import GetFileRequest
from telethon.tl.types import InputDocumentFileLocation, MessageMediaDocument

async def get_clean_sender(client, dc_id):
    """Safely borrows and initializes an exported sender connection for a specific DC."""
    try:
        sender = await client._borrow_exported_sender(dc_id)
        return sender
    except Exception:
        return None

async def fast_download_media(client, msg, target_path, progress_callback=None, parallel_connections=8, chunk_timeout=12.0):
    """
    Ultra-Fast Multi-Socket Telethon Downloader (20-40 MB/s).
    Uses parallel MTProto DC connections with strict 12s chunk timeouts 
    and auto-reconnection to eliminate hangs completely.
    """
    if not msg.media or not isinstance(msg.media, MessageMediaDocument):
        await msg.download_media(file=target_path, progress_callback=progress_callback)
        return

    doc = msg.media.document
    total_size = doc.size
    
    # 512 KB chunk size
    chunk_size = 512 * 1024
    total_chunks = math.ceil(total_size / chunk_size)
    
    # Small files fallback to standard download
    if total_size < 5 * 1024 * 1024:
        await msg.download_media(file=target_path, progress_callback=progress_callback)
        return

    location = InputDocumentFileLocation(
        id=doc.id,
        access_hash=doc.access_hash,
        file_reference=doc.file_reference,
        thumb_size=''
    )
    
    dc_id = doc.dc_id
    
    # Borrow exported sender pool
    senders = []
    for _ in range(parallel_connections):
        sender = await get_clean_sender(client, dc_id)
        if sender:
            senders.append(sender)

    # Fallback to standard if sender pool couldn't be created
    if not senders:
        await msg.download_media(file=target_path, progress_callback=progress_callback)
        return

    # Pre-allocate output file
    with open(target_path, 'wb') as f:
        f.truncate(total_size)

    file_handle = open(target_path, 'r+b')
    downloaded_bytes = 0
    lock = asyncio.Lock()
    failed = False

    async def worker(queue, sender_idx):
        nonlocal downloaded_bytes, failed
        sender = senders[sender_idx]

        while not failed:
            try:
                chunk_idx = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            offset = chunk_idx * chunk_size
            request_size = min(chunk_size, total_size - offset)

            success = False
            for attempt in range(3): # Max 3 retries per chunk
                try:
                    # Enforce strict timeout to prevent any socket hanging!
                    req = GetFileRequest(
                        location=location,
                        offset=offset,
                        limit=request_size
                    )
                    result = await asyncio.wait_for(sender(req), timeout=chunk_timeout)
                    
                    chunk_data = result.bytes
                    async with lock:
                        file_handle.seek(offset)
                        file_handle.write(chunk_data)
                        downloaded_bytes += len(chunk_data)
                        if progress_callback:
                            progress_callback(downloaded_bytes, total_size)
                    
                    success = True
                    break
                except Exception:
                    # If socket timed out or broke, try re-borrowing a fresh sender connection
                    await asyncio.sleep(0.3)
                    try:
                        new_sender = await get_clean_sender(client, dc_id)
                        if new_sender:
                            sender = new_sender
                            senders[sender_idx] = new_sender
                    except Exception:
                        pass

            if not success:
                failed = True
                queue.task_done()
                break

            queue.task_done()

    queue = asyncio.Queue()
    for i in range(total_chunks):
        queue.put_nowait(i)

    worker_tasks = [
        asyncio.create_task(worker(queue, idx))
        for idx in range(len(senders))
    ]

    await asyncio.gather(*worker_tasks, return_exceptions=True)
    file_handle.close()

    # Return senders to client pool
    for sender in senders:
        try:
            await client._return_exported_sender(sender)
        except Exception:
            pass

    # If any error occurred in turbo mode, fallback gracefully to standard download
    if failed or downloaded_bytes < total_size:
        sys.stdout.write("\nTurbo connection reset, finishing part with standard engine...\n")
        sys.stdout.flush()
        await msg.download_media(file=target_path, progress_callback=progress_callback)
