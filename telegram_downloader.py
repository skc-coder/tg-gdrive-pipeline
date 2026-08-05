import os
import asyncio
from telethon import TelegramClient
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto

# ---------------- CONFIGURATION ----------------
API_ID = 21601842
API_HASH = "b824abd0e19c6c67b0b38ec8d470ba03"
# The channel ID extracted from your link https://web.telegram.org/k/#-2107557406
# Telegram channel IDs starting with -100 are represented as -1002107557406 in Telethon
CHANNEL_ID = -1002107557406
DOWNLOAD_DIR = "./telegram_downloads"
# -----------------------------------------------

async def progress_callback(current, total):
    """Prints download progress in percentage."""
    percentage = (current / total) * 100
    print(f"\rDownloading: {percentage:.2f}% ({current}/{total} bytes)", end="", flush=True)

async def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    # Create Telethon client instance
    client = TelegramClient('telegram_session', API_ID, API_HASH)
    await client.start()
    
    print(f"Connected successfully!")
    print(f"Fetching media files from channel ID: {CHANNEL_ID}...")

    try:
        # Get entity for the private channel/group
        entity = await client.get_entity(CHANNEL_ID)
    except Exception as e:
        print(f"\nFailed to resolve channel entity directly: {e}")
        print("Attempting to search in your joined dialogs/chats...")
        entity = None
        async for dialog in client.iter_dialogs():
            if str(dialog.id) == str(CHANNEL_ID) or str(dialog.id) == str(CHANNEL_ID).replace('-100', '-'):
                entity = dialog.entity
                break

    if not entity:
        print("Could not find the target channel in your joined chats.")
        await client.disconnect()
        return

    count = 0
    async for message in client.iter_messages(entity):
        # Check if message contains downloadable media (documents, videos, photos, files)
        if message.media:
            filename = None
            if isinstance(message.media, MessageMediaDocument) and message.file and message.file.name:
                filename = message.file.name
            
            print(f"\n\n[{message.id}] Found media" + (f": {filename}" if filename else ""))

            try:
                path = await message.download_media(
                    file=DOWNLOAD_DIR,
                    progress_callback=progress_callback
                )
                print(f"\nSuccessfully saved to: {path}")
                count += 1
            except Exception as download_err:
                print(f"\nFailed to download message {message.id}: {download_err}")

    print(f"\n\nCompleted! Downloaded {count} file(s) to '{DOWNLOAD_DIR}'.")
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
