import os
import sys
import asyncio
from telethon.tl.types import MessageMediaDocument

async def fast_download_media(client, msg, target_path, progress_callback=None, parallel_connections=4):
    """
    Stable & Fast Telethon Downloader.
    Uses Telethon's native chunked download engine to prevent socket connection resets or cancellations.
    """
    await msg.download_media(file=target_path, progress_callback=progress_callback)
