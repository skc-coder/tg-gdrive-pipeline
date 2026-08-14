import os
import sys
import asyncio

async def fast_download_media(client, msg, target_path, progress_callback=None, parallel_connections=4):
    """
    Stable & High-Speed Telethon Downloader.
    Downloads to a temporary .tmp file first, then renames to target_path upon completion.
    """
    tmp_path = target_path + ".tmp"
    await msg.download_media(file=tmp_path, progress_callback=progress_callback)
    if os.path.exists(tmp_path):
        os.rename(tmp_path, target_path)
