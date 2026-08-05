import os
import sys
import glob
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

# Google Drive remote name configured in rclone (e.g. "gdrive:GATE_Courses")
RCLONE_REMOTE = "gdrive:GATE_Courses"

# Parallel upload threads for rclone
RCLONE_TRANSFERS = "4"

# Directories
WORK_DIR = os.path.abspath("./pipeline_work")
ZIP_DIR = os.path.join(WORK_DIR, "zips")
EXTRACT_DIR = os.path.join(WORK_DIR, "extracted")
STATE_FILE = os.path.join(WORK_DIR, "state.json")
LOG_FILE = os.path.join(WORK_DIR, "pipeline.log")

# =======================================================

def log(msg):
    """Helper to log messages to console and file."""
    text = f"[LOG] {msg}"
    print(text, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(text + "\n")

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"Error reading state file: {e}")
    return {"completed_subjects": [], "failed_subjects": []}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)

def parse_subject_name(filename):
    """
    Extracts subject name from filenames like:
    'C Programming.zip.001' -> 'C Programming'
    'Operating System.zip.004' -> 'Operating System'
    'Computer Organization & Architecture.zip.001' -> 'Computer Organization & Architecture'
    """
    match = re.match(r"^(.*?)\.(zip|7z|rar)(\.\d+)?$", filename, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    base = os.path.splitext(filename)[0]
    return base.strip()

async def progress_callback(current, total):
    percentage = (current / total) * 100
    sys.stdout.write(f"\rDownloading part: {percentage:.2f}% ({current / (1024*1024):.1f}/{total / (1024*1024):.1f} MB)")
    sys.stdout.flush()

def extract_multipart_zip_stream(zip_folder, subject_name):
    """
    Extracts multi-part split zips (e.g. .001, .002, .003) by concatenating 
    them on-the-fly and streaming directly into 7z pipe!
    Zero extra local disk space required for raw zip storage during extraction!
    """
    log(f"Extracting multi-part volumes for '{subject_name}' using streaming pipe (0 extra disk space)...")
    
    # Get all sorted parts (.001, .002, etc.)
    parts = sorted([os.path.join(zip_folder, f) for f in os.listdir(zip_folder) if not f.endswith(".tmp")])
    if not parts:
        raise FileNotFoundError(f"No zip parts found in {zip_folder}")

    log(f"Stream-joining {len(parts)} parts into 7z: {[os.path.basename(p) for p in parts]}")

    # Cat command to join stream
    cat_cmd = ["cat"] + parts
    
    target_extract_dir = os.path.join(EXTRACT_DIR, subject_name)
    os.makedirs(target_extract_dir, exist_ok=True)

    # 7z command reading from STDIN (-)
    sevenz_cmd = ["7z", "x", "-si", f"-o{target_extract_dir}", "-y"]

    p1 = subprocess.Popen(cat_cmd, stdout=subprocess.PIPE)
    p2 = subprocess.Popen(sevenz_cmd, stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    p1.stdout.close() # Allow p1 to receive a SIGPIPE if p2 exits

    stdout, stderr = p2.communicate()

    if p2.returncode != 0:
        log(f"7z Pipe extraction failed! Error output:\n{stderr}")
        raise RuntimeError(f"Streaming extraction failed for {subject_name}")

    log(f"Successfully stream-extracted {subject_name} into '{target_extract_dir}'!")

def upload_folder_and_stream_files(local_folder, subject_name):
    """Uploads extracted folder to Google Drive using rclone in parallel."""
    remote_target = f"{RCLONE_REMOTE}/{subject_name}"
    log(f"Uploading '{subject_name}' to GDrive: {remote_target} with {RCLONE_TRANSFERS} parallel transfers...")

    cmd = [
        "rclone", "copy",
        local_folder,
        remote_target,
        "--transfers", RCLONE_TRANSFERS,
        "--checkers", "8",
        "--stats", "10s",
        "-P"
    ]

    res = subprocess.run(cmd)
    if res.returncode != 0:
        raise RuntimeError(f"Rclone upload failed for {subject_name}")
    log(f"Upload complete for {subject_name}!")

async def main():
    os.makedirs(WORK_DIR, exist_ok=True)
    os.makedirs(ZIP_DIR, exist_ok=True)
    os.makedirs(EXTRACT_DIR, exist_ok=True)

    state = load_state()
    log("="*50)
    log("Starting Stream-Extraction & Cloud-Upload Pipeline")
    log(f"Completed subjects so far: {state['completed_subjects']}")
    log("="*50)

    client = TelegramClient('telegram_session', API_ID, API_HASH)
    await client.start()

    log("Fetching message list from Telegram channel...")
    
    entity = None
    try:
        entity = await client.get_entity(CHANNEL_ID)
    except Exception:
        async for dialog in client.iter_dialogs():
            if str(dialog.id) == str(CHANNEL_ID) or str(dialog.id) == str(CHANNEL_ID).replace('-100', '-'):
                entity = dialog.entity
                break

    if not entity:
        log("ERROR: Could not locate Telegram channel!")
        await client.disconnect()
        return

    # Group messages by subject
    subject_messages = defaultdict(list)
    
    async for message in client.iter_messages(entity):
        if message.media and isinstance(message.media, MessageMediaDocument):
            if message.file and message.file.name:
                fname = message.file.name
                subject = parse_subject_name(fname)
                subject_messages[subject].append((fname, message))

    log(f"Found {len(subject_messages)} distinct subjects in channel:")
    for subj, msgs in subject_messages.items():
        log(f" - {subj}: {len(msgs)} parts")

    for subject, msgs in subject_messages.items():
        if subject in state["completed_subjects"]:
            log(f"\n[SKIP] Subject '{subject}' already processed & uploaded. Skipping.")
            continue

        log(f"\n" + "="*40)
        log(f"PROCESSING SUBJECT: {subject} ({len(msgs)} file parts)")
        log("="*40)

        # Sort parts numerically (.001, .002...)
        msgs.sort(key=lambda x: x[0])

        subj_zip_dir = os.path.join(ZIP_DIR, subject)
        subj_extract_dir = os.path.join(EXTRACT_DIR, subject)
        
        if os.path.exists(subj_zip_dir):
            shutil.rmtree(subj_zip_dir)
        if os.path.exists(subj_extract_dir):
            shutil.rmtree(subj_extract_dir)

        os.makedirs(subj_zip_dir, exist_ok=True)

        try:
            # 1. DOWNLOAD ALL ZIP PARTS FOR THIS SUBJECT
            log(f"Downloading all {len(msgs)} parts for '{subject}'...")
            for fname, msg in msgs:
                target_file_path = os.path.join(subj_zip_dir, fname)
                log(f"\nDownloading part: {fname}")
                await msg.download_media(file=target_file_path, progress_callback=progress_callback)
            print() # New line

            # 2. STREAM-EXTRACT WITHOUT EXTRA DISK COPY
            # (Concatenates parts directly into 7z via stdin pipe `cat .00* | 7z x -si`)
            extract_multipart_zip_stream(subj_zip_dir, subject)

            # 3. DELETE RAW ZIPS IMMEDIATELY TO FREE UP DISK SPACE
            log(f"Deleting raw zip files for '{subject}' to free space...")
            shutil.rmtree(subj_zip_dir)

            # 4. PARALLEL UPLOAD TO GOOGLE DRIVE VIA RCLONE
            log(f"Uploading extracted lectures for '{subject}' to Google Drive...")
            upload_folder_and_stream_files(subj_extract_dir, subject)

            # 5. DELETE EXTRACTED FOLDER TO FREE DISK SPACE
            log(f"Deleting local extracted files for '{subject}'...")
            shutil.rmtree(subj_extract_dir)

            # 6. MARK AS COMPLETED IN STATE
            state["completed_subjects"].append(subject)
            save_state(state)
            log(f"[SUCCESS] Subject '{subject}' fully processed, uploaded, and disk cleaned!")

        except Exception as e:
            log(f"[ERROR] Failed processing subject '{subject}': {e}")
            state["failed_subjects"].append(subject)
            save_state(state)
            if os.path.exists(subj_zip_dir):
                shutil.rmtree(subj_zip_dir)
            if os.path.exists(subj_extract_dir):
                shutil.rmtree(subj_extract_dir)

    log("\nAll subjects processed!")
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
