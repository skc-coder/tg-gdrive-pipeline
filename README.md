# Telegram Channel to Google Drive Pipeline

Automated tool to download multi-part split zips from Telegram channels, extract them on-the-fly, and upload lectures to Google Drive in parallel, optimized for GitHub Codespaces.

## Quick Start on GitHub Codespaces

1. **Run Setup Script** (Installs 7zip, Rclone, virtualenv, and configures GDrive):
   ```bash
   bash setup.sh
   ```

2. **Run Pipeline**:
   ```bash
   ./venv/bin/python main.py
   ```

## Fast Commands

### Pull Latest Code & Run Script (Use this to update and run):
```bash
git pull && ./venv/bin/python main.py
```

### Or Pull, Setup Dependencies & Run:
```bash
git pull && bash setup.sh && ./venv/bin/python main.py
```

## Quick Start on GitHub Codespaces

## Features
- **45GB `/tmp` Storage Optimization**: Handles massive 15GB–30GB subjects cleanly.
- **Stream Pipe Extraction**: ZERO extra disk overhead when extracting `.zip.001`, `.zip.002` split archives.
- **Parallel Google Drive Uploads**: Uses 5 parallel threads (`rclone`) for fast transfers.
- **Automatic Disk Cleanup**: Deletes zips and extracted files immediately after upload.
- **Smart Resume / State Persistence**: Saves progress in `pipeline_data/state.json`. If disconnected, re-running skips completed subjects.
