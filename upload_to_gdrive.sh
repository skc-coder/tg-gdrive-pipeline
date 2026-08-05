#!/bin/bash

# Robust Module-by-Module Sequenced Uploader
# Uploads Module 01, then Module 02, then Module 03... strictly in order.
# Safely handles spaces in folder names and exits properly on Ctrl+C.

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
echo " Starting Module-by-Module Sequential Upload"
echo " Local Path:   $LOCAL_PATH"
echo " Target Drive: $DESTINATION"
echo " Strategy:     Module 01 -> 02 -> 03 ... in strict sequence"
echo "===================================================="
echo ""

# Store directories in array to handle spaces cleanly
mapfile -t MODULE_DIRS < <(find "$LOCAL_PATH" -mindepth 1 -maxdepth 1 -type d | sort)
TOTAL_MODULES=${#MODULE_DIRS[@]}

if [ $TOTAL_MODULES -eq 0 ]; then
    echo "No module subdirectories found in $LOCAL_PATH"
    exit 1
fi

CURRENT=0
for MODULE_DIR in "${MODULE_DIRS[@]}"; do
    CURRENT=$((CURRENT + 1))
    MODULE_NAME=$(basename "$MODULE_DIR")
    
    echo "===================================================="
    echo " [$CURRENT/$TOTAL_MODULES] Syncing: $MODULE_NAME"
    echo "===================================================="
    
    rclone copy "$MODULE_DIR" "$DESTINATION/$MODULE_NAME" \
        --progress \
        --transfers 3 \
        --checkers 6 \
        --drive-chunk-size 64M \
        --drive-upload-cutoff 8M \
        --drive-acknowledge-abuse \
        --timeout 30s \
        --contimeout 15s \
        --low-level-retries 10 \
        --tpslimit 10 \
        --update \
        --exclude "*.crdownload" \
        --exclude "*.part" \
        --exclude "*.tmp" \
        --retries 5 \
        --stats 2s

    EXIT_CODE=$?
    
    if [ $EXIT_CODE -ne 0 ]; then
        echo ""
        echo "--> Upload stopped/interrupted on [$MODULE_NAME] (exit code: $EXIT_CODE)."
        exit $EXIT_CODE
    fi
    
    echo ""
    echo "--> Finished [$MODULE_NAME]"
    echo ""
done

echo "===================================================="
echo " All $TOTAL_MODULES modules uploaded successfully!"
echo "===================================================="
