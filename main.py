import os
import sys
import time
import json
import re
import subprocess
import asyncio
import shutil
import sqlite3
from collections import defaultdict
from telethon import TelegramClient
from telethon.tl.types import MessageMediaDocument

from fast_download import fast_download_media

# ==================== CONFIGURATION ====================
API_ID = 21601842
API_HASH = "b824abd0e19c6c67b0b38ec8d470ba03"
CHANNEL_ID = -1002107557406

# Google Drive remote name configured in rclone (e.g. "gdrive:GATE_Courses")
RCLONE_REMOTE = "gdrive:GATE_Courses"

# Parallel upload threads for rclone
RCLONE_TRANSFERS = "5"

# Max parallel file downloads (3 files at once)
MAX_PARALLEL_DOWNLOADS = 3

# Subject processing order specified by user (Digital Logic then Algorithms at the very end)
PRIORITY_ORDER = [
    "Operating System",
    "Data Structures",
    "Compiler Design",
    "C Programming",
    "Digital Logic",
    "Algorithms"
]

# Explicitly excluded subjects
EXCLUDED_SUBJECTS = [
    "Computer Organization & Architecture",
    "COA"
]

# Temporary storage partition (/tmp has ~45GB in GitHub Codespaces)
TEMP_STORAGE_DIR = "/tmp/tg_pipeline"
ZIP_DIR = os.path.join(TEMP_STORAGE_DIR, "zips")
EXTRACT_DIR = os.path.join(TEMP_STORAGE_DIR, "extracted")

# Persistent storage paths in workspace root
WORKSPACE_DIR = os.path.abspath("./pipeline_data")
STATE_FILE = os.path.join(WORKSPACE_DIR, "state.json")
LOG_FILE = os.path.join(WORKSPACE_DIR, "pipeline.log")
# =======================================================

def log(msg):
    text = f"[LOG] {msg}"
    print(text, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(text + "\n")

def cleanup_stale_session_locks():
    journal_file = os.path.abspath("telegram_session.session-journal")
    if os.path.exists(journal_file):
        try:
            os.remove(journal_file)
            log("Removed orphaned sqlite session-journal file.")
        except Exception:
            pass

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
    cleaned = re.sub(r'(\.(zip|7z|rar|\d{3}))+$', '', filename, flags=re.IGNORECASE).strip()
    return cleaned if cleaned else filename

def get_subject_priority(subject):
    for idx, p in enumerate(PRIORITY_ORDER):
        if p.lower() in subject.lower():
            return idx
    return 999

def find_existing_file(subj_zip_dir, fname, expected_size=None):
    """Detects existing completed files on disk."""
    if not os.path.exists(subj_zip_dir):
        return None

    direct = os.path.join(subj_zip_dir, fname)
    if os.path.exists(direct) and os.path.getsize(direct) > 0:
        if expected_size is None or os.path.getsize(direct) >= expected_size:
            return direct

    match = re.search(r'(\.\d{3})$', fname)
    part_ext = match.group(1) if match else None

    for existing_f in os.listdir(subj_zip_dir):
        full_p = os.path.join(subj_zip_dir, existing_f)
        if os.path.isfile(full_p) and os.path.getsize(full_p) > 0:
            if expected_size is None or os.path.getsize(full_p) >= expected_size:
                if part_ext and existing_f.endswith(part_ext):
                    return full_p
                if existing_f == fname or fname in existing_f:
                    return full_p
    return None

def make_bar(percentage, length=10):
    filled = int(length * percentage / 100)
    bar = "█" * filled + "░" * (length - filled)
    return bar

class ParallelProgressManager:
    """Manages clean inline multi-line progress rendering without line wrapping."""
    def __init__(self):
        self.stats = {}
        self.running = False
        self.rendered_lines = 0

    def update(self, fname, current, total):
        now = time.time()
        if fname not in self.stats:
            self.stats[fname] = {'start': now, 'current': current, 'total': total, 'speed': 0.0}
        else:
            st = self.stats[fname]
            elapsed = max(now - st['start'], 0.001)
            st['current'] = current
            st['total'] = total
            st['speed'] = (current / (1024 * 1024)) / elapsed

    def finish(self, fname):
        if fname in self.stats:
            self.stats[fname]['completed'] = True

    async def render_loop(self):
        self.running = True
        while self.running:
            self.render()
            await asyncio.sleep(0.4)
        self.render()

    def format_time(self, seconds):
        if seconds < 0 or seconds == float('inf'):
            return "--:--"
        secs = int(seconds)
        mins, s = divmod(secs, 60)
        hrs, m = divmod(mins, 60)
        if hrs > 0:
            return f"{hrs:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def render(self):
        if not self.stats:
            return

        if self.rendered_lines > 0:
            sys.stdout.write(f"\x1b[{self.rendered_lines}A")

        lines = ["\x1b[KActive Parallel Downloads:"]
        total_remaining_bytes = 0
        total_speed_mb = 0.0

        for fname, st in list(self.stats.items()):
            curr_bytes = st['current']
            tot_bytes = st['total']
            curr_mb = curr_bytes / (1024 * 1024)
            total_mb = tot_bytes / (1024 * 1024) if tot_bytes > 0 else 1.0
            pct = (curr_bytes / tot_bytes * 100) if tot_bytes > 0 else 0.0
            speed = st.get('speed', 0.0)
            bar = make_bar(pct, length=10)

            if st.get('completed'):
                status_str = "DONE"
            else:
                rem_bytes = max(0, tot_bytes - curr_bytes)
                total_remaining_bytes += rem_bytes
                total_speed_mb += speed
                speed_bytes = speed * 1024 * 1024
                eta_sec = (rem_bytes / speed_bytes) if speed_bytes > 0 else float('inf')
                eta_str = self.format_time(eta_sec)
                status_str = f"{speed:4.1f} MB/s | ETA: {eta_str}"
            
            short_name = fname if len(fname) <= 18 else fname[:8] + "..." + fname[-7:]
            line = f"\x1b[K  ├─ {short_name:<18} [{bar}] {pct:5.1f}% | {curr_mb:4.0f}/{total_mb:4.0f}MB | {status_str}"
            lines.append(line[:85])

        if total_speed_mb > 0 and total_remaining_bytes > 0:
            tot_speed_bytes = total_speed_mb * 1024 * 1024
            total_eta_sec = total_remaining_bytes / tot_speed_bytes
            tot_eta_str = self.format_time(total_eta_sec)
            lines.append(f"\x1b[K  └─ Overall Speed: {total_speed_mb:4.1f} MB/s | Total Time Remaining: {tot_eta_str}".rstrip()[:85])

        out = "\n".join(lines) + "\n"
        sys.stdout.write(out)
        sys.stdout.flush()
        self.rendered_lines = len(lines)

    def stop(self):
        self.running = False

async def download_part_task(client, msg, target_path, semaphore, manager):
    fname = os.path.basename(target_path)
    async with semaphore:
        def cb(current, total):
            manager.update(fname, current, total)
            
        await fast_download_media(client, msg, target_path, progress_callback=cb, parallel_connections=6)
        manager.finish(fname)

def extract_nested_archives(folder_path):
    """
    Recursively checks for nested .zip, .7z, or .rar files inside folder_path,
    extracts them further, and deletes the archive files.
    """
    archive_found = True
    while archive_found:
        archive_found = False
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in ['.zip', '.7z', '.rar']:
                    archive_path = os.path.join(root, file)
                    log(f"Found nested archive '{file}' inside '{root}'. Extracting further...")
                    
                    cmd = ["7z", "x", archive_path, f"-o{root}", "-y"]
                    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    if res.returncode == 0:
                        log(f"Successfully extracted nested archive '{file}'!")
                        try:
                            os.remove(archive_path)
                            log(f"Deleted nested archive file '{file}' to free space.")
                        except Exception as e:
                            log(f"Warning: Could not remove nested archive '{file}': {e}")
                        archive_found = True
                        break
                    else:
                        log(f"Warning: Failed to extract nested archive '{file}': {res.stderr}")
            if archive_found:
                break

def extract_multipart_zip(zip_folder, subject_name):
    """Extracts split multi-part zips (.001, .002...) cleanly with 7z and handles nested zips."""
    target_extract_dir = os.path.join(EXTRACT_DIR, subject_name)
    os.makedirs(target_extract_dir, exist_ok=True)
    
    parts = sorted([os.path.join(zip_folder, f) for f in os.listdir(zip_folder) if not f.endswith(".tmp")])
    if not parts:
        raise FileNotFoundError(f"No zip parts found in {zip_folder}")

    first_part = parts[0]
    for p in parts:
        if p.endswith(".001") or p.endswith(".zip"):
            first_part = p
            break

    log(f"Extracting multi-part archive starting from '{os.path.basename(first_part)}'...")

    cmd = ["7z", "x", first_part, f"-o{target_extract_dir}", "-y"]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if res.returncode != 0:
        log(f"7z Extraction error:\n{res.stderr}")
        raise RuntimeError(f"Extraction failed for {subject_name}")

    log(f"Successfully extracted split volumes for '{subject_name}'!")
    
    # Delete original multi-part zips immediately to free disk space!
    try:
        shutil.rmtree(zip_folder)
        log(f"Deleted downloaded multi-part zips in '{zip_folder}' to free disk space!")
    except Exception as e:
        log(f"Warning: Could not remove multi-part zip folder: {e}")

    # Extract any nested zips found inside the extracted folder
    extract_nested_archives(target_extract_dir)

def upload_to_gdrive_parallel(local_folder, subject_name):
    remote_target = f"{RCLONE_REMOTE}/{subject_name}"
    log(f"Uploading '{subject_name}' to GDrive ({remote_target}) with {RCLONE_TRANSFERS} parallel workers...")

    cmd = [
        "rclone", "copy",
        local_folder,
        remote_target,
        "--transfers", RCLONE_TRANSFERS,
        "--checkers", "10",
        "--fast-list",
        "--stats", "10s",
        "-P"
    ]

    res = subprocess.run(cmd)
    if res.returncode != 0:
        raise RuntimeError(f"Rclone upload failed for {subject_name}")
    log(f"Upload completed for {subject_name}!")

def process_pending_extractions(state):
    """Checks /tmp/tg_pipeline/extracted/ for unuploaded folders, extracts nested zips, and uploads them."""
    if not os.path.exists(EXTRACT_DIR):
        return

    extracted_folders = [d for d in os.listdir(EXTRACT_DIR) if os.path.isdir(os.path.join(EXTRACT_DIR, d))]
    if not extracted_folders:
        return

    log(f"Found {len(extracted_folders)} pending extracted folder(s) in /tmp: {extracted_folders}")
    for subject in extracted_folders:
        if subject in state["completed_subjects"]:
            log(f"Skipping already completed subject '{subject}'.")
            continue

        log(f"\nProcessing pending extracted folder: {subject}")
        subj_extract_dir = os.path.join(EXTRACT_DIR, subject)

        try:
            # 1. Extract any inner nested zips
            extract_nested_archives(subj_extract_dir)

            # 2. Upload to Google Drive
            upload_to_gdrive_parallel(subj_extract_dir, subject)

            # 3. Clean up folder
            shutil.rmtree(subj_extract_dir)

            # 4. Save state
            state["completed_subjects"].append(subject)
            save_state(state)
            log(f"[SUCCESS] Pending subject '{subject}' extracted further, uploaded, and cleaned!")
        except Exception as e:
            log(f"[ERROR] Processing pending folder '{subject}' failed: {e}")

async def main():
    cleanup_stale_session_locks()
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    os.makedirs(ZIP_DIR, exist_ok=True)
    os.makedirs(EXTRACT_DIR, exist_ok=True)

    state = load_state()
    log("="*60)
    log(f"GitHub Codespaces Pipeline (Priority Processing & Nested Zip Extraction)")
    log(f"Completed subjects so far: {state['completed_subjects']}")
    log("="*60)

    # First, process any pending extracted folders sitting in /tmp
    process_pending_extractions(state)

    client = TelegramClient('telegram_session', API_ID, API_HASH)

    try:
        await client.start()
    except sqlite3.OperationalError as e:
        log(f"SQLite lock error detected: {e}")
        log("Attempting session recovery...")
        cleanup_stale_session_locks()
        await asyncio.sleep(1)
        await client.start()

    log("Fetching Telegram channel message list...")
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

    subject_messages = defaultdict(list)
    async for message in client.iter_messages(entity):
        if message.media and isinstance(message.media, MessageMediaDocument):
            if message.file and message.file.name:
                fname = message.file.name
                subject = parse_subject_name(fname)
                
                if any(ex.lower() in subject.lower() for ex in EXCLUDED_SUBJECTS):
                    continue
                    
                subject_messages[subject].append((fname, message))

    sorted_subjects = sorted(subject_messages.keys(), key=get_subject_priority)

    log(f"Discovered {len(sorted_subjects)} distinct subjects (Sorted by Priority):")
    for idx, subj in enumerate(sorted_subjects, 1):
        log(f" {idx}. {subj}: {len(subject_messages[subj])} parts")

    semaphore = asyncio.Semaphore(MAX_PARALLEL_DOWNLOADS)

    for subject in sorted_subjects:
        msgs = subject_messages[subject]
        
        if subject in state["completed_subjects"]:
            log(f"\n[SKIP] Subject '{subject}' already completed.")
            continue

        log(f"\n" + "="*50)
        log(f"PROCESSING SUBJECT: {subject} ({len(msgs)} file parts)")
        log("="*50)

        msgs.sort(key=lambda x: x[0])

        subj_zip_dir = os.path.join(ZIP_DIR, subject)
        subj_extract_dir = os.path.join(EXTRACT_DIR, subject)

        legacy_zip_dir = subj_zip_dir + ".zip"
        if os.path.exists(legacy_zip_dir):
            os.makedirs(subj_zip_dir, exist_ok=True)
            for f in os.listdir(legacy_zip_dir):
                shutil.move(os.path.join(legacy_zip_dir, f), os.path.join(subj_zip_dir, f))
            shutil.rmtree(legacy_zip_dir)
            log(f"Merged legacy folder '{legacy_zip_dir}' into '{subj_zip_dir}'")

        os.makedirs(subj_zip_dir, exist_ok=True)

        files_to_download = []
        for fname, msg in msgs:
            expected_size = msg.media.document.size if (msg.media and hasattr(msg.media, 'document')) else None
            existing = find_existing_file(subj_zip_dir, fname, expected_size=expected_size)
            if existing:
                size_mb = os.path.getsize(existing) / (1024 * 1024)
                log(f" [SKIP FILE] Found completed part '{os.path.basename(existing)}' ({size_mb:.1f} MB) on disk.")
            else:
                target_path = os.path.join(subj_zip_dir, fname)
                files_to_download.append((fname, msg, target_path))

        try:
            if not files_to_download:
                log(f"[ALL FILES PRESENT] All {len(msgs)} zip parts for '{subject}' are present on disk! Proceeding straight to extraction...")
            else:
                log(f"Downloading {len(files_to_download)} remaining parts in parallel...")
                manager = ParallelProgressManager()
                render_task = asyncio.create_task(manager.render_loop())

                download_tasks = []
                for fname, msg, target_path in files_to_download:
                    download_tasks.append(download_part_task(client, msg, target_path, semaphore, manager))

                await asyncio.gather(*download_tasks)
                manager.stop()
                await render_task
                print("\nDownload complete for all remaining parts!")

            # 2. Extract multi-part zips (.001, .002...) and any inner nested zips
            extract_multipart_zip(subj_zip_dir, subject)

            # 3. Delete raw zips immediately to free space in /tmp
            log(f"Cleaning raw zips for '{subject}'...")
            shutil.rmtree(subj_zip_dir)

            # 4. Upload extracted files in 5 parallel transfers to Google Drive via rclone
            upload_to_gdrive_parallel(subj_extract_dir, subject)

            # 5. Delete extracted files from /tmp
            log(f"Cleaning extracted files for '{subject}'...")
            shutil.rmtree(subj_extract_dir)

            # 6. Save persistent state
            state["completed_subjects"].append(subject)
            save_state(state)
            log(f"[SUCCESS] '{subject}' completed, uploaded to GDrive, and space cleaned!")

        except Exception as e:
            log(f"[ERROR] Subject '{subject}' failed: {e}")
            state["failed_subjects"].append(subject)
            save_state(state)

    log("\nAll priority subjects successfully processed!")
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
