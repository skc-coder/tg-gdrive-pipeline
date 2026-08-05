#!/bin/bash

# High-Performance Fast Google Drive Sync Script
# Starts uploading instantly without scanning delays.

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
echo " Transfers:    4 Files in Parallel (Videos & PDFs)"
echo "===================================================="
echo ""

rclone copy "$LOCAL_PATH" "$DESTINATION" \
    --progress \
    --transfers 10 \
    --checkers 15 \
    --drive-chunk-size 32M \
    --drive-upload-cutoff 8M \
    --drive-acknowledge-abuse \
    --timeout 30s \
    --contimeout 15s \
    --low-level-retries 10 \
    --update \
    --exclude "*.crdownload" \
    --exclude "*.part" \
    --exclude "*.tmp" \
    --retries 5 \
    --stats 1s

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
