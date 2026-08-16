# Telegram Channel to Google Drive Pipeline

Automated tool to download files, videos, and multi-part split zips from Telegram channels, extract them on-the-fly, and upload them to Google Drive in parallel, optimized for GitHub Codespaces.

---

## 📋 How to Add / Configure Your Channels

Channels are configured in `channels.json` in the root folder. You can add as many channels as you want:

```json
[
    {
        "channel_id": -1002107557406,
        "remote_folder": "GATE_Courses",
        "name": "Primary GATE Channel"
    },
    {
        "channel_id": -1001234567890,
        "remote_folder": "Physics_Lectures",
        "name": "Physics Channel"
    }
]
```

- **`channel_id`**: The Telegram channel ID (e.g. `-1002107557406` or `@channel_username`).
- **`remote_folder`**: The subfolder in Google Drive where files from this channel will be saved.
- **`name`**: Friendly name for logs and status UI.

---

## 🚀 How to Pull & Run (Exact Commands)

To pull the latest code update and run the pipeline immediately:

```bash
git pull && ./venv/bin/python main.py
```

Or step by step:
```bash
git pull
./venv/bin/python main.py
```

---

## ⚡ Features
- **General File Support**: Works for PDFs, Videos (MP4), Documents, and ZIP files.
- **Smart Disk Management**: Auto-flushes & uploads to Google Drive if `/tmp` storage drops below 8GB.
- **Standard Telegram Speeds**: Uses 3 parallel downloads to prevent speed throttling.
- **5 Parallel Rclone Uploads**: Transfers to Google Drive concurrently.
- **Multi-Part & Recursive Extraction**: Automatically extracts `.zip.001` split archives and inner nested zips.
- **Live Terminal Dashboard**: Shows active download ETA/speed, upload status, and free disk space.
- **State Resuming**: Keeps track of processed messages in `pipeline_data/state.json`.


