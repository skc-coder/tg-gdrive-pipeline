import os
import sys
import json
import re
import subprocess
import asyncio
import shutil
from collections import defaultdict
from telethon import TelegramClient
from telethon.tl.types import MessageMediaDocument

# ==================== CONFIGURATION ====================
API_ID = 21601842
API_HASH = "b824abd0e19c6c67b0b38ec8d470ba03"
CHANNEL_ID = -1002107557406

# Target Google Drive Mount Path (Mounted via rclone mount)
GDRIVE_MOUNT_DIR = os.path.abspath("./gdrive_mount")
TARGET_COURSE_DIR = os.path.join(GDRIVE_MOUNT_DIR, "GATE_Courses")

STATE_FILE = os.path.abspath("./pipeline_state.json")
LOG_FILE = os.path.abspath("./pipeline.log")
# =======================================================

def log(msg):
    text = f"[LOG] {msg}"
    print(text, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(text + "\n")

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"completed_subjects": [], "failed_subjects": []}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)

def parse_subject_name(filename):
    match = re.match(r"^(.*?)\.(zip|7z|rar)(\.\d+)?$", filename, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return os.path.splitext(filename)[0].strip()

async def progress_callback(current, total):
    percentage = (current / total) * 100
    sys.stdout.write(f"\rDownloading to GDrive Mount: {percentage:.2f}% ({current / (1024*1024):.1f}/{total / (1024*1024):.1f} MB)")
    sys.stdout.flush()

def extract_in_gdrive(subject_zip_dir, subject_extract_dir, subject_name):
    log(f"Extracting multi-part volumes directly inside GDrive for '{subject_name}'...")
    
    parts = sorted([os.path.join(subject_zip_dir, f) for f in os.listdir(subject_zip_dir)])
    if not parts:
        raise FileNotFoundError(f"No parts found in {subject_zip_dir}")

    first_part = parts[0]
    log(f"Starting extraction from: {os.path.basename(first_part)}")

    # Extract directly into GDrive target folder
    cmd = ["7z", "x", first_part, f"-o{subject_extract_dir}", "-y"]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if res.returncode != 0:
        log(f"7z extraction error:\n{res.stderr}")
        raise RuntimeError(f"Extraction failed for {subject_name}")
    
    log(f"Successfully extracted '{subject_name}' directly on Google Drive!")

async def main():
    state = load_state()

    # Check if Google Drive is mounted
    if not os.path.exists(GDRIVE_MOUNT_DIR) or not os.listdir(GDRIVE_MOUNT_DIR):
        log("ERROR: Google Drive is not mounted at './gdrive_mount'!")
        log("Please run this command first in background to mount your GDrive:")
        log("mkdir -p gdrive_mount && rclone mount gdrive: gdrive_mount --vfs-cache-mode full &")
        return

    os.makedirs(TARGET_COURSE_DIR, exist_ok=True)

    log("="*50)
    log("Starting Zero-Local-Disk Telegram Downloader")
    log("="*50)

    client = TelegramClient('telegram_session', API_ID, API_HASH)
    await client.start()

    entity = None
    try:
        entity = await client.get_entity(CHANNEL_ID)
    except Exception:
        async for dialog in client.iter_dialogs():
            if str(dialog.id) == str(CHANNEL_ID) or str(dialog.id) == str(CHANNEL_ID).replace('-100', '-'):
                entity = dialog.entity
                break

    if not entity:
        log("ERROR: Channel entity not found!")
        await client.disconnect()
        return

    subject_messages = defaultdict(list)
    async for message in client.iter_messages(entity):
        if message.media and isinstance(message.media, MessageMediaDocument):
            if message.file and message.file.name:
                fname = message.file.name
                subject = parse_subject_name(fname)
                subject_messages[subject].append((fname, message))

    for subject, msgs in subject_messages.items():
        if subject in state["completed_subjects"]:
            log(f"\n[SKIP] '{subject}' already completed.")
            continue

        log(f"\n" + "="*40)
        log(f"PROCESSING SUBJECT (0-DISK USAGE): {subject}")
        log("="*40)

        msgs.sort(key=lambda x: x[0])

        # Directories directly inside GDrive Mount!
        subj_zip_gdrive = os.path.join(TARGET_COURSE_DIR, subject, "_temp_zips")
        subj_extract_gdrive = os.path.join(TARGET_COURSE_DIR, subject, "Lectures")

        os.makedirs(subj_zip_gdrive, exist_ok=True)
        os.makedirs(subj_extract_gdrive, exist_ok=True)

        try:
            # 1. Download directly into GDrive
            for fname, msg in msgs:
                target = os.path.join(subj_zip_gdrive, fname)
                if not os.path.exists(target):
                    log(f"\nDownloading part direct to GDrive: {fname}")
                    await msg.download_media(file=target, progress_callback=progress_callback)
            print()

            # 2. Extract directly inside GDrive
            extract_in_gdrive(subj_zip_gdrive, subj_extract_gdrive, subject)

            # 3. Delete temporary zips from GDrive
            log(f"Deleting raw zip files from GDrive for '{subject}'...")
            shutil.rmtree(subj_zip_gdrive)

            # 4. Mark complete
            state["completed_subjects"].append(subject)
            save_state(state)
            log(f"[SUCCESS] '{subject}' downloaded & extracted directly on GDrive!")

        except Exception as e:
            log(f"[ERROR] Subject '{subject}' failed: {e}")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
