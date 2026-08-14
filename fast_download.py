import os
import sys
import asyncio

async def download_chunk(client, msg, start, end, file_handle, progress_cb, fname):
    """Downloads a specific byte range offset over a separate connection."""
    downloaded = 0
    async for chunk in client.iter_download(msg.media, offset=start, limit=end - start):
        file_handle.seek(start + downloaded)
        file_handle.write(chunk)
        downloaded += len(chunk)
        if progress_cb:
            progress_cb(start + downloaded)

async def fast_download_media(client, msg, target_path, progress_callback=None, parallel_connections=8):
    """
    Parallel Chunked Downloader for Telethon.
    Splits the Telegram file into N parallel connections, bypassing Telegram's 3MB/s single-stream throttling!
    """
    if not msg.media or not hasattr(msg.media, 'document'):
        await msg.download_media(file=target_path, progress_callback=progress_callback)
        return

    total_size = msg.media.document.size
    chunk_size = total_size // parallel_connections

    # Create target file with full size
    with open(target_path, "wb") as f:
        f.truncate(total_size)

    progress_dict = {}

    def chunk_progress_builder(chunk_idx):
        def cb(current_chunk_pos):
            progress_dict[chunk_idx] = current_chunk_pos - (chunk_idx * chunk_size)
            if progress_callback:
                progress_callback(sum(progress_dict.values()), total_size)
        return cb

    tasks = []
    with open(target_path, "r+b") as f:
        for i in range(parallel_connections):
            start = i * chunk_size
            end = total_size if i == parallel_connections - 1 else (i + 1) * chunk_size
            tasks.append(download_chunk(client, msg, start, end, f, chunk_progress_builder(i), os.path.basename(target_path)))
        await asyncio.gather(*tasks)
