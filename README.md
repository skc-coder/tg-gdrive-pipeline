# Telegram Channel to Google Drive Pipeline

Automated tool to download multi-part split zips from Telegram channels, extract them on-the-fly, and upload lectures to Google Drive in parallel, optimized for GitHub Codespaces.

---

## 🚀 How to Launch the Server / Pipeline

### 1. Initial Setup (First Time Only)
Run the setup script to install dependencies (`7zip`, `rclone`, `virtualenv`) and configure Google Drive access:
```bash
bash setup.sh
```

### 2. Launch the Pipeline / Server
To start the pipeline execution:
```bash
./venv/bin/python main.py
```

### 3. Quick Pull & Run Command
If you want to pull the latest changes from Git and run the server immediately:
```bash
git pull && ./venv/bin/python main.py
```

---

## 📤 How to Git Push (Saving & Uploading Changes)

When you make changes to the codebase and want to push them to GitHub:

### Step 1: Check modified files
```bash
git status
```

### Step 2: Stage changes
```bash
git add .
```

### Step 3: Commit changes with a message
```bash
git commit -m "Your descriptive commit message"
```

### Step 4: Push changes to GitHub
```bash
git push
```

*Note: If pushing for the first time on a new branch, use `git push -u origin <branch-name>`.*

---

## ⚡ Features
- **45GB `/tmp` Storage Optimization**: Handles massive 15GB–30GB subjects cleanly.
- **Stream Pipe Extraction**: ZERO extra disk overhead when extracting `.zip.001`, `.zip.002` split archives.
- **Parallel Google Drive Uploads**: Uses 5 parallel threads (`rclone`) for fast transfers.
- **Automatic Disk Cleanup**: Deletes zips and extracted files immediately after upload.
- **Smart Resume / State Persistence**: Saves progress in `pipeline_data/state.json`. If disconnected, re-running skips completed subjects.

