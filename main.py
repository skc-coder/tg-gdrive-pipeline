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

# ==================== CONFIGURATION ====================
API_ID = 21601842
API_HASH = "b824abd0e19c6c67b0b38ec8d470ba03"

# List of Telegram channels to process in order
# Can also be managed via channels.json file in the root directory!
DEFAULT_CHANNELS = [
    {
        "channel_id": -1002107557406,
        "remote_folder": "GATE_Courses",
        "name": "Primary GATE Channel"
    }
]

CHANNELS_FILE = os.path.abspath("channels.json")

def load_channels():
    if os.path.exists(CHANNELS_FILE):
        try:
            with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
                chans = json.load(f)
                if isinstance(chans, list) and len(chans) > 0:
                    return chans
        except Exception as e:
            print(f"[WARNING] Could not parse channels.json: {e}")
    # Write default channels.json if it doesn't exist
    try:
        with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CHANNELS, f, indent=4)
    except Exception:
        pass
    return DEFAULT_CHANNELS

CHANNELS = load_channels()


# Base Google Drive rclone remote
RCLONE_REMOTE = "gdrive:"

# Parallel upload threads for rclone
RCLONE_TRANSFERS = 5

# Max parallel file downloads from Telegram (using standard Telethon)
MAX_PARALLEL_DOWNLOADS = 3

# Storage safety thresholds (in Bytes) for /tmp partition (~40GB total on Codespaces)
# If free disk space drops below MIN_FREE_DISK_BYTES, downloads pause until uploads clean space.
MIN_FREE_DISK_BYTES = 8 * 1024 * 1024 * 1024  # 8 GB minimum free buffer

# Temporary storage partitions
TEMP_STORAGE_DIR = "/tmp/tg_pipeline"
DOWNLOAD_DIR = os.path.join(TEMP_STORAGE_DIR, "downloads")
EXTRACT_DIR = os.path.join(TEMP_STORAGE_DIR, "extracted")

# Persistent state & logs
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
    state = {
        "completed_channels": [],
        "downloaded_msg_ids": {},
        "uploaded_files": {},
    }
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    state.update(loaded)
        except Exception:
            pass
    if "completed_channels" not in state:
        state["completed_channels"] = []
    if "downloaded_msg_ids" not in state:
        state["downloaded_msg_ids"] = {}
    if "uploaded_files" not in state:
        state["uploaded_files"] = {}
    return state


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)

def make_bar(percentage, length=10):
    filled = int(length * max(0.0, min(100.0, percentage)) / 100)
    return "█" * filled + "░" * (length - filled)

def format_time(seconds):
    if seconds < 0 or seconds == float('inf') or math.isnan(seconds):
        return "--:--"
    secs = int(seconds)
    mins, s = divmod(secs, 60)
    hrs, m = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

import math

class StatusTracker:
    def __init__(self):
        self.downloads = {}  # fname -> {start, current, total, speed, completed}
        self.uploads = {}    # fname -> {start, current, total, speed, status}
        self.rendered_lines = 0
        self.running = False

    def update_download(self, fname, current, total):
        now = time.time()
        if fname not in self.downloads:
            self.downloads[fname] = {'start': now, 'current': current, 'total': total, 'speed': 0.0, 'completed': False}
        else:
            st = self.downloads[fname]
            elapsed = max(now - st['start'], 0.001)
            st['current'] = current
            st['total'] = total
            st['speed'] = (current / (1024 * 1024)) / elapsed

    def finish_download(self, fname):
        if fname in self.downloads:
            self.downloads[fname]['completed'] = True

    def update_upload(self, fname, current, total, status="Uploading"):
        now = time.time()
        if fname not in self.uploads:
            self.uploads[fname] = {'start': now, 'current': current, 'total': total, 'speed': 0.0, 'status': status}
        else:
            st = self.uploads[fname]
            elapsed = max(now - st['start'], 0.001)
            st['current'] = current
            st['total'] = total
            st['speed'] = (current / (1024 * 1024)) / elapsed
            st['status'] = status

    def finish_upload(self, fname):
        if fname in self.uploads:
            self.uploads[fname]['status'] = "DONE"
            self.uploads[fname]['current'] = self.uploads[fname]['total']

    async def render_loop(self):
        self.running = True
        while self.running:
            self.render()
            await asyncio.sleep(0.5)
        self.render()

    def render(self):
        total, used, free = shutil.disk_usage(TEMP_STORAGE_DIR)
        free_gb = free / (1024 ** 3)
        total_gb = total / (1024 ** 3)

        lines = []
        lines.append(f"\x1b[K=================== PIPELINE STATUS Dashboard ===================")
        lines.append(f"\x1b[KStorage (/tmp): {free_gb:.1f} GB free of {total_gb:.1f} GB | Min Buffer: {MIN_FREE_DISK_BYTES/(1024**3):.1f} GB")
        
        # Download section
        active_dl = {k: v for k, v in self.downloads.items() if not v.get('completed')}
        lines.append(f"\x1b[KActive Downloads ({len(active_dl)} / {MAX_PARALLEL_DOWNLOADS}):")
        tot_dl_speed = 0.0
        tot_dl_rem = 0
        for fname, st in list(active_dl.items())[-MAX_PARALLEL_DOWNLOADS:]:
            curr_bytes = st['current']
            tot_bytes = st['total']
            pct = (curr_bytes / tot_bytes * 100) if tot_bytes > 0 else 0.0
            speed = st.get('speed', 0.0)
            tot_dl_speed += speed
            rem_b = max(0, tot_bytes - curr_bytes)
            tot_dl_rem += rem_b
            eta = format_time(rem_b / (speed * 1024 * 1024)) if speed > 0 else "--:--"
            bar = make_bar(pct, length=10)
            sname = fname if len(fname) <= 20 else fname[:9] + "..." + fname[-8:]
            lines.append(f"\x1b[K  [DL] {sname:<20} [{bar}] {pct:5.1f}% | {curr_bytes/(1024**2):4.0f}/{tot_bytes/(1024**2):4.0f}MB | {speed:4.1f}MB/s | ETA:{eta}")

        if tot_dl_speed > 0:
            overall_dl_eta = format_time(tot_dl_rem / (tot_dl_speed * 1024 * 1024))
            lines.append(f"\x1b[K  └─ Total Download Speed: {tot_dl_speed:4.1f} MB/s | Combined ETA: {overall_dl_eta}")

        # Upload section
        active_ul = {k: v for k, v in self.uploads.items() if v.get('status') != "DONE"}
        lines.append(f"\x1b[KActive Uploads ({len(active_ul)} / {RCLONE_TRANSFERS} workers):")
        for fname, st in list(active_ul.items())[-RCLONE_TRANSFERS:]:
            curr_bytes = st['current']
            tot_bytes = st['total']
            pct = (curr_bytes / tot_bytes * 100) if tot_bytes > 0 else 0.0
            speed = st.get('speed', 0.0)
            status = st.get('status', 'Uploading')
            bar = make_bar(pct, length=10)
            sname = fname if len(fname) <= 20 else fname[:9] + "..." + fname[-8:]
            lines.append(f"\x1b[K  [UL] {sname:<20} [{bar}] {pct:5.1f}% | {status} | {speed:4.1f}MB/s")

        lines.append(f"\x1b[K================================================================")

        if self.rendered_lines > 0:
            sys.stdout.write(f"\x1b[{self.rendered_lines}A")

        out = "\n".join(lines) + "\n"
        sys.stdout.write(out)
        sys.stdout.flush()
        self.rendered_lines = len(lines)

    def stop(self):
        self.running = False

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

def extract_multipart_zip_if_needed(file_path_or_dir, extract_to):
    """
    Handles zip files (single or split multi-part .001, .zip).
    If it's a zip/multipart zip, extracts it to extract_to and deletes the original zip(s).
    If it's a normal file (PDF, MP4, etc.), moves it to extract_to directly.
    """
    os.makedirs(extract_to, exist_ok=True)
    if os.path.isdir(file_path_or_dir):
        # Folder containing download parts
        parts = sorted([os.path.join(file_path_or_dir, f) for f in os.listdir(file_path_or_dir) if not f.endswith(".tmp")])
        if not parts:
            return
        
        # Check if files inside are zip / archive parts
        first_file = parts[0]
        ext = os.path.splitext(first_file)[1].lower()
        if ext in ['.zip', '.001', '.7z', '.rar', '.z01']:
            log(f"Extracting multipart archive in '{file_path_or_dir}' to '{extract_to}'...")
            cmd = ["7z", "x", first_file, f"-o{extract_to}", "-y"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                log(f"Successfully extracted multipart archive!")
                shutil.rmtree(file_path_or_dir, ignore_errors=True)
                extract_nested_archives(extract_to)
            else:
                log(f"Extraction failed: {res.stderr}")
        else:
            # Not a zip archive, move all regular files to extract_to
            for p in parts:
                dest = os.path.join(extract_to, os.path.basename(p))
                shutil.move(p, dest)
            shutil.rmtree(file_path_or_dir, ignore_errors=True)
    else:
        # Single file
        ext = os.path.splitext(file_path_or_dir)[1].lower()
        if ext in ['.zip', '.7z', '.rar']:
            log(f"Extracting single archive '{file_path_or_dir}' to '{extract_to}'...")
            cmd = ["7z", "x", file_path_or_dir, f"-o{extract_to}", "-y"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                log(f"Successfully extracted '{file_path_or_dir}'!")
                os.remove(file_path_or_dir)
                extract_nested_archives(extract_to)
            else:
                log(f"Failed extracting '{file_path_or_dir}': {res.stderr}")
                dest = os.path.join(extract_to, os.path.basename(file_path_or_dir))
                shutil.move(file_path_or_dir, dest)
        else:
            dest = os.path.join(extract_to, os.path.basename(file_path_or_dir))
            shutil.move(file_path_or_dir, dest)

async def upload_folder_gdrive(local_folder, remote_target_path, status_tracker=None):
    """Uploads local_folder to GDrive using rclone with 5 parallel transfers."""
    log(f"Uploading '{local_folder}' to GDrive path '{remote_target_path}'...")
    
    cmd = [
        "rclone", "copy",
        local_folder,
        remote_target_path,
        "--transfers", str(RCLONE_TRANSFERS),
        "--checkers", "10",
        "--fast-list",
        "--stats", "5s",
        "-P"
    ]
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    fname = os.path.basename(local_folder)
    if status_tracker:
        status_tracker.update_upload(fname, 0, 100, status="Uploading...")

    stdout, stderr = await proc.communicate()
    
    if proc.returncode != 0:
        log(f"Rclone upload error:\n{stderr.decode()}")
        raise RuntimeError(f"Rclone upload failed for {local_folder}")
    
    if status_tracker:
        status_tracker.finish_upload(fname)
    log(f"Upload complete for '{local_folder}'!")

async def process_channel(client, channel_info, state, status_tracker):
    channel_id = channel_info["channel_id"]
    remote_folder = channel_info["remote_folder"]
    channel_name = channel_info["name"]
    chan_key = str(channel_id)

    log("="*60)
    log(f"STARTING CHANNEL: {channel_name} (ID: {channel_id}) -> GDrive: {RCLONE_REMOTE}/{remote_folder}")
    log("="*60)

    if chan_key not in state["downloaded_msg_ids"]:
        state["downloaded_msg_ids"][chan_key] = []
    if chan_key not in state["uploaded_files"]:
        state["uploaded_files"][chan_key] = []

    entity = None
    try:
        entity = await client.get_entity(channel_id)
    except Exception:
        async for dialog in client.iter_dialogs():
            if str(dialog.id) == chan_key or str(dialog.id) == chan_key.replace('-100', '-'):
                entity = dialog.entity
                break

    if not entity:
        log(f"ERROR: Could not find Telegram entity for channel {channel_id}")
        return

    # Fetch messages with document media
    messages_to_process = []
    async for message in client.iter_messages(entity):
        if message.media and isinstance(message.media, MessageMediaDocument):
            if message.file and message.file.name:
                if message.id not in state["downloaded_msg_ids"][chan_key]:
                    messages_to_process.append(message)

    messages_to_process.reverse() # Process oldest to newest
    log(f"Found {len(messages_to_process)} pending media messages in channel '{channel_name}'.")

    dl_semaphore = asyncio.Semaphore(MAX_PARALLEL_DOWNLOADS)
    
    chan_dl_dir = os.path.join(DOWNLOAD_DIR, chan_key)
    chan_ext_dir = os.path.join(EXTRACT_DIR, chan_key)
    os.makedirs(chan_dl_dir, exist_ok=True)
    os.makedirs(chan_ext_dir, exist_ok=True)

    async def download_worker(msg):
        fname = msg.file.name
        target_path = os.path.join(chan_dl_dir, fname)

        # Check storage space on /tmp before downloading
        _, _, free_bytes = shutil.disk_usage(TEMP_STORAGE_DIR)
        if free_bytes < MIN_FREE_DISK_BYTES:
            log(f"DISK SPACE LOW ({free_bytes / (1024**3):.2f} GB free). Pausing download...")
            while shutil.disk_usage(TEMP_STORAGE_DIR)[2] < MIN_FREE_DISK_BYTES:
                await asyncio.sleep(5)

        async with dl_semaphore:
            def dl_cb(current, total):
                status_tracker.update_download(fname, current, total)

            log(f"Downloading message {msg.id}: {fname}...")
            await msg.download_media(file=target_path, progress_callback=dl_cb)
            status_tracker.finish_download(fname)
            
            # Track state
            state["downloaded_msg_ids"][chan_key].append(msg.id)
            save_state(state)

        # After download, extract zip / prepare for upload
        extract_multipart_zip_if_needed(target_path, chan_ext_dir)

    # Launch parallel downloads batch
    tasks = [download_worker(m) for m in messages_to_process]
    await asyncio.gather(*tasks)


    # Final upload of remaining extracted files for this channel
    if os.path.exists(chan_ext_dir) and os.listdir(chan_ext_dir):
        remote_target = f"{RCLONE_REMOTE}/{remote_folder}"
        await upload_folder_gdrive(chan_ext_dir, remote_target, status_tracker)
        shutil.rmtree(chan_ext_dir, ignore_errors=True)

    if chan_key not in state["completed_channels"]:
        state["completed_channels"].append(chan_key)
        save_state(state)

    log(f"FINISHED CHANNEL: {channel_name}!")

async def main():
    cleanup_stale_session_locks()
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(EXTRACT_DIR, exist_ok=True)

    state = load_state()
    log("="*60)
    log("Starting General Telegram to Google Drive Pipeline")
    log(f"Completed Channels: {state['completed_channels']}")
    log("="*60)

    client = TelegramClient('telegram_session', API_ID, API_HASH)

    try:
        await client.start()
    except sqlite3.OperationalError as e:
        log(f"SQLite lock error: {e}. Recovering...")
        cleanup_stale_session_locks()
        await asyncio.sleep(1)
        await client.start()

    status_tracker = StatusTracker()
    render_task = asyncio.create_task(status_tracker.render_loop())

    try:
        for channel_info in CHANNELS:
            await process_channel(client, channel_info, state, status_tracker)
    finally:
        status_tracker.stop()
        await render_task
        await client.disconnect()
        log("Pipeline execution finished cleanly.")

if __name__ == '__main__':
    asyncio.run(main())
