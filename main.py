import os
import sys
import time
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
RCLONE_TRANSFERS = "5"

# Max parallel file downloads (3 files at once)
MAX_PARALLEL_DOWNLOADS = 3

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

def make_bar(percentage, length=20):
    filled = int(length * percentage / 100)
    bar = "█" * filled + "░" * (length - filled)
    return bar

class ParallelProgressManager:
    """Manages clean inline multi-line progress rendering without terminal bloat."""
    def __init__ (self):
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

    def render(self):
        if not self.stats:
            return

        # Move cursor back up to overwrite previous rendered lines
        if self.rendered_lines > 0:
            sys.stdout.write(f"\x1b[{self.rendered_lines}A")

        lines = []
        lines.append("\x1b[K Active Parallel Downloads:")
        for fname, st in list(self.stats.items()):
            curr_mb = st['current'] / (1024 * 1024)
            total_mb = st['total'] / (1024 * 1024) if st['total'] > 0 else 1.0
            pct = (st['current'] / st['total'] * 100) if st['total'] > 0 else 0.0
            speed = st.get('speed', 0.0)
            bar = make_bar(pct, length=15)
            status_str = "DONE" if st.get('completed') else f"{speed:5.1f} MB/s"
            
            # Truncate filename if too long for clean display
            short_name = fname if len(fname) <= 30 else fname[:14] + "..." + fname[-13:]
            lines.append(f"\x1b[K  ├─ {short_name:<30} [{bar}] {pct:5.1f}% | {curr_mb:6.1f}/{total_mb:6.1f} MB | {status_str}")

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
            
        await client.download_media(file=target_path, progress_callback=cb)
        manager.finish(fname)

def extract_multipart_zip_stream(zip_folder, subject_name):
    log(f"Stream-extracting volumes for '{subject_name}' into /tmp...")
    
    parts = sorted([os.path.join(zip_folder, f) for f in os.listdir(zip_folder) if not f.endswith(".tmp")])
    if not parts:
        raise FileNotFoundError(f"No zip parts found in {zip_folder}")

    target_extract_dir = os.path.join(EXTRACT_DIR, subject_name)
    os.makedirs(target_extract_dir, exist_ok=True)

    log(f"Found {len(parts)} parts for extraction: {[os.path.basename(p) for p in parts]}")

    cat_cmd = ["cat"] + parts
    sevenz_cmd = ["7z", "x", "-si", f"-o{target_extract_dir}", "-y"]

    p1 = subprocess.Popen(cat_cmd, stdout=subprocess.PIPE)
    p2 = subprocess.Popen(sevenz_cmd, stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    p1.stdout.close()

    stdout, stderr = p2.communicate()

    if p2.returncode != 0:
        log(f"7z Extraction error:\n{stderr}")
        raise RuntimeError(f"Extraction failed for {subject_name}")

    log(f"Successfully stream-extracted '{subject_name}'!")

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

async def main():
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    os.makedirs(ZIP_DIR, exist_ok=True)
    os.makedirs(EXTRACT_DIR, exist_ok=True)

    state = load_state()
    log("="*60)
    log(f"GitHub Codespaces Pipeline (Parallel Downloads: {MAX_PARALLEL_DOWNLOADS})")
    log(f"Completed subjects so far: {state['completed_subjects']}")
    log("="*60)

    client = TelegramClient('telegram_session', API_ID, API_HASH)
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
                subject_messages[subject].append((fname, message))

    log(f"Discovered {len(subject_messages)} distinct subjects:")
    for subj, msgs in subject_messages.items():
        log(f" - {subj}: {len(msgs)} parts")

    semaphore = asyncio.Semaphore(MAX_PARALLEL_DOWNLOADS)

    for subject, msgs in subject_messages.items():
        if subject in state["completed_subjects"]:
            log(f"\n[SKIP] Subject '{subject}' already completed.")
            continue

        log(f"\n" + "="*50)
        log(f"PROCESSING SUBJECT: {subject} ({len(msgs)} file parts)")
        log("="*50)

        msgs.sort(key=lambda x: x[0])

        subj_zip_dir = os.path.join(ZIP_DIR, subject)
        subj_extract_dir = os.path.join(EXTRACT_DIR, subject)

        if os.path.exists(subj_zip_dir):
            shutil.rmtree(subj_zip_dir)
        if os.path.exists(subj_extract_dir):
            shutil.rmtree(subj_extract_dir)

        os.makedirs(subj_zip_dir, exist_ok=True)

        try:
            # 1. PARALLEL DOWNLOAD WITH CLEAN INLINE DASHBOARD
            log(f"Downloading {len(msgs)} parts in parallel (Concurrency limit: {MAX_PARALLEL_DOWNLOADS})...")
            manager = ParallelProgressManager()
            render_task = asyncio.create_task(manager.render_loop())

            download_tasks = []
            for fname, msg in msgs:
                target_path = os.path.join(subj_zip_dir, fname)
                download_tasks.append(download_part_task(client, msg, target_path, semaphore, manager))

            await asyncio.gather(*download_tasks)
            manager.stop()
            await render_task
            print("\nDownload complete for all parts!")

            # 2. Extract multi-part zips using stream pipe into /tmp
            extract_multipart_zip_stream(subj_zip_dir, subject)

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
            if os.path.exists(subj_zip_dir):
                shutil.rmtree(subj_zip_dir)
            if os.path.exists(subj_extract_dir):
                shutil.rmtree(subj_extract_dir)

    log("\nAll subjects successfully processed!")
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
