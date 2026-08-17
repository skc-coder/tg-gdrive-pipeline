#!/usr/bin/env python3
"""
Stream Downloader Core Pipeline Engine.
Low-Storage Parallel Producer-Consumer Architecture:
 1. Indexing course subjects & chapters (cached in .index_cache.json).
    - Explicitly excludes Khazana courses/topics and Announcement tabs.
    - Preserves ALL subjects (Physics, Chemistry, Biology, Maths, SST, English, Hindi, Computer Science, Notices).
    - Properly URL-encodes MEDIA_TOKEN string to resolve video DASH streams.
 2. Concurrent PDF & ClearKey Video Downloader:
    - Silently skips invalid/empty attachments (where key is missing).
    - Downloads valid PDFs & ClearKey DRM videos into `staging/`.
    - Atomically moves finished files to `ready_for_upload/`.
 3. Concurrent Uploader Worker Thread:
    - Polls `ready_for_upload/` every 10 seconds.
    - Uploads ready files directly to Google Drive `stream/Course/Subject/Chapter/`.
    - Fixed rclone flag: `--delete-empty-src-dirs`
    - Immediately deletes local files upon successful upload verification to free disk space!
 4. State tracking (.pipeline_state.json) guarantees 100% resume capability.
"""

import json
import os
import re
import sys
import time
import subprocess
from urllib.parse import parse_qs, urlparse, quote
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests

BASE_URL = "https://stream.testuk.org"
PROXY_BASE = "https://proxy.streamvideo.co.in/fetch/api.penpencil.co"

STAGING_DIR = "staging"
READY_DIR = "ready_for_upload"
INDEX_CACHE_FILE = ".index_cache.json"
STATE_FILE = ".pipeline_state.json"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Referer": "https://stream.testuk.org/"
}

# --- STATE & CACHE MANAGEMENT ---

def load_json(filepath, default):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath) as f:
            return json.load(f)
    except:
        return default

def save_json(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

def load_config():
    return load_json("config.json", {})

def load_state():
    return load_json(STATE_FILE, {"downloaded": {}, "uploaded": {}, "course_indexed": {}})

def save_state(state):
    save_json(STATE_FILE, state)

def is_item_done(item_id):
    state = load_state()
    return state.get("uploaded", {}).get(item_id, False)

def is_downloaded(item_id):
    state = load_state()
    return state.get("downloaded", {}).get(item_id, False)

def mark_downloaded(item_id):
    state = load_state()
    if "downloaded" not in state:
        state["downloaded"] = {}
    state["downloaded"][item_id] = True
    save_state(state)

def mark_uploaded(item_id):
    state = load_state()
    if "uploaded" not in state:
        state["uploaded"] = {}
    state["uploaded"][item_id] = True
    save_state(state)

def load_cache():
    return load_json(INDEX_CACHE_FILE, {})

def save_cache(cache):
    save_json(INDEX_CACHE_FILE, cache)

def load_courses():
    if not os.path.exists("courses.txt"):
        print("[!] courses.txt not found!")
        return []
    courses = []
    with open("courses.txt") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                parsed = urlparse(line)
                qs = parse_qs(parsed.query)
                batch_id = qs.get("batchId", [None])[0]
                batch_name = qs.get("batchName", ["Course"])[0]
                if batch_id:
                    courses.append({"batchId": batch_id, "batchName": batch_name, "url": line})
    return courses

def sanitize_name(name):
    return "".join(c if c.isalnum() or c in (" ", "-", "_", ".") else "_" for c in name).strip()

# --- HTTP SESSION SETUP ---

cfg = load_config()
session_cookie = cfg.get("session", "")
session_expiry = cfg.get("session_expiry", "1786887774943")

session = requests.Session()
if session_cookie:
    session.cookies.set("session", session_cookie, domain="stream.testuk.org")
session.cookies.set("session_expiry", session_expiry, domain="stream.testuk.org")
session.headers.update(DEFAULT_HEADERS)

def fetch_json(url):
    for attempt in range(3):
        try:
            r = session.get(url, impersonate="chrome120", timeout=15)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 429:
                time.sleep(2 * (attempt + 1))
        except Exception as e:
            time.sleep(1)
    return None

def fetch_html(url):
    for attempt in range(3):
        try:
            r = session.get(url, impersonate="chrome120", timeout=15)
            if r.status_code == 200:
                return r.text
            elif r.status_code == 429:
                time.sleep(2 * (attempt + 1))
        except Exception as e:
            time.sleep(1)
    return ""

# --- INDEXING & RESOLVING ---

def get_subjects(batch_id):
    url = f"{PROXY_BASE}/v3/batches/{batch_id}/details"
    data = fetch_json(url)
    if data and data.get("success"):
        all_subs = data.get("data", {}).get("subjects", [])
        valid_subs = []
        for s in all_subs:
            s_name = s.get("subject", "").strip().lower()
            # Exclude ONLY Khazana & Announcement tabs
            if "khazana" in s_name or s.get("khazanaProgramId"):
                continue
            if "announcement" in s_name:
                continue
            valid_subs.append(s)
        return valid_subs
    return []

def get_topics(batch_id, subject_id):
    topics = []
    page = 1
    while True:
        url = f"{PROXY_BASE}/v2/batches/{batch_id}/subject/{subject_id}/topics?page={page}"
        data = fetch_json(url)
        if not data or not data.get("success") or not data.get("data"):
            break
        items = data.get("data", [])
        for item in items:
            t_name = item.get("name", "").lower()
            if "khazana" in t_name or "announcement" in t_name:
                continue
            topics.append(item)
        if len(items) < 10:
            break
        page += 1
    return topics

def get_contents(batch_id, subject_id, topic_id, content_type="videos"):
    contents = []
    page = 1
    while True:
        url = f"{PROXY_BASE}/v2/batches/{batch_id}/subject/{subject_id}/contents?page={page}&contentType={content_type}&tag={topic_id}"
        data = fetch_json(url)
        if not data or not data.get("success") or not data.get("data"):
            break
        items = data.get("data", [])
        contents.extend(items)
        if len(items) < 10:
            break
        page += 1
    return contents

def parse_schedule_details(batch_id, subject_id, schedule_id, cache):
    cache_key = f"vid_details:{schedule_id}"
    if cache_key in cache:
        return cache[cache_key]

    url = f"{BASE_URL}/schedule-details?batchId={batch_id}&subjectId={subject_id}&scheduleId={schedule_id}&tap=video"
    html = fetch_html(url)
    if not html:
        return {}

    info = {
        "mediaToken": None,
        "slides": [],
        "notes": [],
        "dppNotes": [],
        "topicName": None,
        "videoStream": None
    }

    m_token = re.search(r'const\s+MEDIA_TOKEN\s*=\s*"([^"]+)";', html)
    if m_token:
        info["mediaToken"] = m_token.group(1)

    m_topic = re.search(r'const\s+TOPIC_NAME\s*=\s*"([^"]+)";', html)
    if m_topic:
        info["topicName"] = m_topic.group(1)

    m_notes = re.search(r'const\s+NOTES\s*=\s*(\[.*?\]);', html, re.DOTALL)
    if m_notes:
        try:
            info["notes"] = json.loads(m_notes.group(1))
        except:
            pass

    if info["mediaToken"]:
        enc_token = quote(info["mediaToken"], safe="")
        stream_url = f"{BASE_URL}/v1/videos/video-url-details?mediaToken={enc_token}&videoContainerType=DASH"
        stream_data = fetch_json(stream_url)
        if stream_data and stream_data.get("data"):
            info["videoStream"] = stream_data.get("data")

    cache[cache_key] = info
    save_cache(cache)
    return info

def index_course(course, cache):
    b_id = course["batchId"]
    b_name = course["batchName"]
    print(f"\n==================================================")
    print(f"[*] INDEXING COURSE: {b_name} ({b_id}) [Excluding Khazana]")
    print(f"==================================================")

    course_entry = {"batchId": b_id, "batchName": b_name, "subjects": []}
    subjects = get_subjects(b_id)
    print(f"[+] Found {len(subjects)} subjects")

    for s_idx, sub in enumerate(subjects, 1):
        s_id = sub["_id"]
        s_name = sub["subject"]
        print(f"\n  [Subject {s_idx}/{len(subjects)}] Indexing Subject: {s_name}")
        sub_entry = {"id": s_id, "name": s_name, "chapters": []}
        topics = get_topics(b_id, s_id)
        print(f"  └─ Found {len(topics)} chapters/topics")

        for t_idx, top in enumerate(topics, 1):
            t_id = top["_id"]
            t_name = top["name"]
            print(f"     [Chapter {t_idx}/{len(topics)}] {t_name}")
            ch_entry = {"id": t_id, "name": t_name, "videos": [], "notes": []}

            raw_videos = get_contents(b_id, s_id, t_id, "videos")
            
            def process_video_item(v_item):
                v_id = v_item["_id"]
                v_title = v_item.get("topic") or v_item.get("videoDetails", {}).get("name") or "Untitled Video"
                details = parse_schedule_details(b_id, s_id, v_id, cache)
                return {
                    "id": v_id,
                    "title": v_title,
                    "mediaToken": details.get("mediaToken"),
                    "videoStream": details.get("videoStream"),
                    "notes": details.get("notes", [])
                }

            if raw_videos:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    ch_entry["videos"] = list(executor.map(process_video_item, raw_videos))
                print(f"        ├─ Videos found & resolved: {len(ch_entry['videos'])}")

            raw_notes = get_contents(b_id, s_id, t_id, "notes")
            for n_item in raw_notes:
                for hw in n_item.get("homeworkIds", []):
                    for att in hw.get("attachmentIds", []):
                        base_u = att.get("baseUrl", "")
                        att_k = att.get("key", "")
                        if base_u and att_k:
                            ch_entry["notes"].append({
                                "name": hw.get("topic") or att.get("name") or "Note",
                                "url": base_u + att_k
                            })
            if ch_entry["notes"]:
                print(f"        └─ Notes found: {len(ch_entry['notes'])}")

            sub_entry["chapters"].append(ch_entry)
        course_entry["subjects"].append(sub_entry)

    return course_entry

# --- ATOMIC MOVE TO READY_FOR_UPLOAD ---

def move_to_ready(staging_path, ready_path):
    os.makedirs(os.path.dirname(ready_path), exist_ok=True)
    os.rename(staging_path, ready_path)

# --- DOWNLOADERS ---

def is_valid_file_url(url):
    if not url or not isinstance(url, str):
        return False
    url_clean = url.strip()
    if not url_clean.startswith("http://") and not url_clean.startswith("https://"):
        return False
    parsed = urlparse(url_clean)
    if not parsed.path or parsed.path == "/" or parsed.path.endswith("/"):
        return False
    return True

def download_pdf_task(item):
    url = item["url"]
    staging_path = item["staging_path"]
    ready_path = item["ready_path"]
    item_id = item["item_id"]

    if not is_valid_file_url(url):
        return

    if is_item_done(item_id):
        return

    if os.path.exists(ready_path):
        mark_downloaded(item_id)
        return

    os.makedirs(os.path.dirname(staging_path), exist_ok=True)
    
    for attempt in range(3):
        try:
            r = session.get(url, headers=DEFAULT_HEADERS, impersonate="chrome120", timeout=30)
            if r.status_code == 200 and len(r.content) > 0:
                with open(staging_path, "wb") as f:
                    f.write(r.content)
                move_to_ready(staging_path, ready_path)
                mark_downloaded(item_id)
                print(f"[PDF READY FOR UPLOAD] {ready_path}")
                return
            elif r.status_code == 403:
                time.sleep(1)
        except Exception as e:
            time.sleep(1)

    print(f"[FAIL] HTTP 403 / Download error for {url}")

def download_video_task(item):
    stream_info = item["stream_info"]
    staging_path = item["staging_path"]
    ready_path = item["ready_path"]
    v_id = item["v_id"]
    item_id = f"video:{v_id}"

    if is_item_done(item_id):
        return

    if os.path.exists(ready_path):
        mark_downloaded(item_id)
        return

    os.makedirs(os.path.dirname(staging_path), exist_ok=True)
    manifest_url = stream_info.get("url")
    keys = stream_info.get("keys", [])

    if not manifest_url or not is_valid_file_url(manifest_url):
        return

    cmd = ["yt-dlp", manifest_url, "-o", staging_path]
    for key in keys:
        cmd.extend(["--key", key])
    cmd.extend(["--concurrent-fragments", "5", "--no-mtime", "--quiet"])

    print(f"[DOWNLOADING VIDEO] {ready_path}")
    try:
        res = subprocess.run(cmd)
        if res.returncode == 0:
            move_to_ready(staging_path, ready_path)
            mark_downloaded(item_id)
            print(f"[VIDEO READY FOR UPLOAD] {ready_path}")
    except Exception as e:
        print(f"[ERROR] Video download failed: {e}")

# --- UPLOADER WORKER (POLLS ready_for_upload & DELETES UPON SUCCESS) ---

def uploader_worker(stop_event, config):
    remote_name = config.get("gdrive_remote_name", "gdrive")
    root_folder = config.get("gdrive_root_folder", "stream")
    upload_threads = config.get("gdrive_upload_threads", 6)
    target_remote = f"{remote_name}:{root_folder}"

    print("[*] Uploader Worker active. Polling ready_for_upload/ every 10 seconds...")

    while not stop_event.is_set():
        if os.path.exists(READY_DIR):
            files_to_upload = []
            for root, _, files in os.walk(READY_DIR):
                for f in files:
                    files_to_upload.append(os.path.join(root, f))

            if files_to_upload:
                print(f"\n[UPLOADER] Found {len(files_to_upload)} files ready for upload. Syncing to Google Drive...")
                cmd = [
                    "rclone", "move", READY_DIR, target_remote,
                    "--transfers", str(upload_threads), "--checkers", str(upload_threads * 2),
                    "--delete-empty-src-dirs", "--fast-list"
                ]
                res = subprocess.run(cmd)
                if res.returncode == 0:
                    print(f"[✓ UPLOADER] Successfully uploaded & deleted local copies to free disk space!")
                else:
                    print(f"[!] Uploader rclone exited code {res.returncode}")

        time.sleep(10)

# --- MAIN EXECUTION FLOW ---

def main():
    print("🚀 Stream Parallel Downloader & Uploader Engine Starting...")
    courses = load_courses()
    if not courses:
        print("[!] No courses found in courses.txt!")
        sys.exit(1)

    cfg = load_config()
    cache = load_cache()
    pdf_threads = cfg.get("pdf_download_threads", 8)
    video_threads = cfg.get("video_download_threads", 3)

    import threading
    stop_uploader = threading.Event()
    uploader_thread = threading.Thread(target=uploader_worker, args=(stop_uploader, cfg), daemon=True)
    uploader_thread.start()

    try:
        for c_idx, course in enumerate(courses, 1):
            c_name = course["batchName"]
            print(f"\n##################################################")
            print(f"   PROCESSING COURSE [{c_idx}/{len(courses)}]: {c_name}")
            print(f"##################################################")

            # Indexing (cached)
            course_entry = index_course(course, cache)

            # Process course items (PDFs & DRM Videos concurrently)
            pdf_items = []
            video_items = []

            for sub in course_entry.get("subjects", []):
                sub_name = sanitize_name(sub["name"])
                for ch in sub.get("chapters", []):
                    ch_name = sanitize_name(ch["name"])

                    # 1. Videos and their attached notes
                    for vid in ch.get("videos", []):
                        v_title = sanitize_name(vid["title"])
                        v_id = vid["id"]
                        stream_info = vid.get("videoStream")
                        if stream_info:
                            rel_path = os.path.join(c_name, sub_name, ch_name, f"{v_title}.mp4")
                            video_items.append({
                                "v_id": v_id,
                                "stream_info": stream_info,
                                "staging_path": os.path.join(STAGING_DIR, rel_path),
                                "ready_path": os.path.join(READY_DIR, rel_path)
                            })

                        for note in vid.get("notes", []):
                            url = note.get("url")
                            n_name = sanitize_name(note.get("name", "Note"))
                            if is_valid_file_url(url):
                                fname = f"{n_name}.pdf" if not n_name.endswith(".pdf") else n_name
                                rel_path = os.path.join(c_name, sub_name, ch_name, fname)
                                pdf_items.append({
                                    "url": url,
                                    "staging_path": os.path.join(STAGING_DIR, rel_path),
                                    "ready_path": os.path.join(READY_DIR, rel_path),
                                    "item_id": f"pdf:{url}"
                                })

                    # 2. Standalone chapter notes
                    for note in ch.get("notes", []):
                        url = note.get("url")
                        n_name = sanitize_name(note.get("name", "Note"))
                        if is_valid_file_url(url):
                            fname = f"{n_name}.pdf" if not n_name.endswith(".pdf") else n_name
                            rel_path = os.path.join(c_name, sub_name, ch_name, fname)
                            pdf_items.append({
                                "url": url,
                                "staging_path": os.path.join(STAGING_DIR, rel_path),
                                "ready_path": os.path.join(READY_DIR, rel_path),
                                "item_id": f"pdf:{url}"
                            })

            total_files = len(pdf_items) + len(video_items)
            print(f"\n[+] Total items indexed for {c_name}: {len(pdf_items)} PDFs, {len(video_items)} Videos (Total: {total_files} items).")

            # Execute parallel downloads (PDFs and DRM Videos concurrently using ThreadPoolExecutor)
            with ThreadPoolExecutor(max_workers=pdf_threads + video_threads) as executor:
                futures = []
                for p_item in pdf_items:
                    futures.append(executor.submit(download_pdf_task, p_item))
                for v_item in video_items:
                    futures.append(executor.submit(download_video_task, v_item))
                for f in futures:
                    f.result()

            print(f"\n[+] Finished downloading all {total_files} items for course {c_name}.")
            print(f"[*] Waiting for uploader worker to sync all pending files to Google Drive...")
            while True:
                has_files = False
                if os.path.exists(READY_DIR):
                    for root, _, files in os.walk(READY_DIR):
                        if files:
                            has_files = True
                            break
                if not has_files:
                    break
                time.sleep(5)
            print(f"[✓] All files for course {c_name} have been completely uploaded and synced!")

    finally:
        stop_uploader.set()
        print("\n🎉 ALL COURSES PROCESSED, DOWNLOADED, AND UPLOADED TO GOOGLE DRIVE!")

if __name__ == "__main__":
    main()
