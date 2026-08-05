#!/bin/bash
set -e

echo "=================================================="
echo "   Telegram to GDrive Pipeline Quick Setup"
echo "=================================================="

# 1. Update & install system dependencies
echo "[1/4] Installing system packages (p7zip-full, rclone, python3-pip)..."
sudo apt-get update -qq
sudo apt-get install -y -qq p7zip-full rclone python3-pip python3-venv

# 2. Setup Python virtual environment
echo "[2/4] Setting up Python virtual environment..."
python3 -m venv venv
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install telethon pillow -q

# 3. Check Rclone configuration
echo "[3/4] Checking Rclone configuration..."
if ! rclone listremotes | grep -q "^gdrive:"; then
    echo "--------------------------------------------------"
    echo "WARNING: Rclone remote 'gdrive:' is not configured!"
    echo "Please configure rclone now by following the prompts:"
    echo "  1. Type 'n' for new remote"
    echo "  2. Name it: gdrive"
    echo "  3. Storage type: choose 'drive' (Google Drive)"
    echo "--------------------------------------------------"
    rclone config
else
    echo "Rclone remote 'gdrive:' detected!"
fi

echo "=================================================="
echo "Setup complete! To start the pipeline, run:"
echo "  ./venv/bin/python main.py"
echo "=================================================="
