#!/bin/bash

# Cloud Bridge: Sync to Azure Blob Storage
# Uses 'az storage blob upload-batch' with retry logic

# Default Values
SOURCE_DIR=""
CONTAINER_NAME="Thor_Backups"
WATCH_MODE=false
MAX_RETRIES=5

# Parse Arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --source) SOURCE_DIR="$2"; shift ;;
        --container) CONTAINER_NAME="$2"; shift ;;
        --watch) WATCH_MODE=true ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

if [ -z "$SOURCE_DIR" ]; then
    echo "Error: --source argument is required."
    echo "Usage: $0 --source <path> --container <name> [--watch]"
    exit 1
fi

upload_batch() {
    local attempt=1
    local success=false

    echo "[$(date)] Starting upload from '$SOURCE_DIR' to '$CONTAINER_NAME'..."

    while [ $attempt -le $MAX_RETRIES ]; do
        # Run the upload command
        # --if-unmodified-since is not needed for batch, but we use --overwrite true to ensure latest ver
        # We capture output to check for specific error strings if needed
        
        output=$(az storage blob upload-batch \
            --destination "$CONTAINER_NAME" \
            --source "$SOURCE_DIR" \
            --overwrite true \
            --output table 2>&1)
        
        exit_code=$?

        if [ $exit_code -eq 0 ]; then
            echo "[$(date)] Upload successful."
            echo "$output"
            success=true
            break
        else
            echo "[$(date)] Error uploading (Attempt $attempt/$MAX_RETRIES). Exit code: $exit_code"
            echo "Output: $output"
            
            # Simple exponential backoff
            local sleep_time=$(( 2 ** attempt ))
            echo "Retrying in $sleep_time seconds..."
            sleep $sleep_time
            ((attempt++))
        fi
    done

    if [ "$success" = false ]; then
        echo "[$(date)] CRITICAL: Upload failed after $MAX_RETRIES attempts."
        return 1
    fi
}

# Main Execution Flow
if [ "$WATCH_MODE" = true ]; then
    echo "Starting Watch Mode on '$SOURCE_DIR'..."
    ech "Press [CTRL+C] to stop."
    
    # Simple polling loop (every 30 seconds)
    # A more advanced version would use 'inotifywait' on Linux or custom python script, 
    # but strictly using Bash loops for portability in this snippet.
    
    while true; do
        upload_batch
        sleep 30
    done
else
    upload_batch
fi
