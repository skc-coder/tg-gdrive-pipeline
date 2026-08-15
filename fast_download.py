import os
import sys
import asyncio

async def fast_download_media(client, msg, target_path, progress_callback=None, parallel_connections=4):
    """
    Original Stable Telethon Downloader with .tmp protection.
    Uses Telethon's native engine without extra MTProto socket overhead.
    """
    tmp_path = target_path + ".tmp"
    await msg.download_media(file=tmp_path, progress_callback=progress_callback)
    if os.path.exists(tmp_path):
        os.rename(tmp_path, target_path)

