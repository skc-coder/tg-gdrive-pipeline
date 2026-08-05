#!/bin/bash

# High-Performance Fast Google Drive Sync Script
# Uploads ALL files (PDFs, MKVs, PPTs, Docs) in natural name order (Module 01 -> 02 -> 03...)
# Uses 4 parallel transfers so if 1 file stutters, other files & PDFs keep uploading without blocking.

LOCAL_PATH="$1"
REMOTE_NAME="${2:-gdrive}"
DRIVE_FOLDER="${3:-Uploads}"

if [ -z "$LOCAL_PATH" ]; then
    echo "Usage: ./upload_to_gdrive.sh <MASTER_FOLDER_PATH> [REMOTE_NAME] [DRIVE_DESTINATION_FOLDER]"
    exit 1
fi

LOCAL_PATH="${LOCAL_PATH%/}"

if [ ! -d "$LOCAL_PATH" ]; then
    echo "Error: Directory '$LOCAL_PATH' does not exist."
    exit 1
fi

FOLDER_NAME=$(basename "$LOCAL_PATH")
DESTINATION="$REMOTE_NAME:$DRIVE_FOLDER/$FOLDER_NAME"

echo "===================================================="
echo " Starting Fast Parallel Google Drive Upload"
echo " Local Path:   $LOCAL_PATH"
echo " Target Drive: $DESTINATION"
echo " Transfers:    4 Files in Parallel (Includes PDFs & Videos)"
echo " Order:        Module 01 -> 02 -> 03 ... (Sequential Priority)"
echo "===================================================="
echo ""

rclone copy "$LOCAL_PATH" "$DESTINATION" \
    --progress \
    --transfers 4 \
    --checkers 8 \
    --order-by "name,ascending" \
    --fast-list \
    --drive-chunk-size 32M \
    --drive-upload-cutoff 8M \
    --drive-acknowledge-abuse \
    --drive-pacer-min-sleep 10ms \
    --timeout 20s \
    --contimeout 10s \
    --low-level-retries 10 \
    --tpslimit 12 \
    --update \
    --exclude "*.crdownload" \
    --exclude "*.part" \
    --exclude "*.tmp" \
    --retries 5 \
    --stats 2s

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "===================================================="
    echo " SUCCESS: All modules, videos, and PDFs uploaded!"
    echo "===================================================="
else
    echo ""
    echo "Upload encountered error (Exit Code: $EXIT_CODE)."
fi

exit $EXIT_CODE
