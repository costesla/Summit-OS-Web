---
name: cloud-bridge
description: Bridges local file systems to Azure Blob Storage using the Azure CLI. Includes retry logic and directory monitoring.
---

# Cloud Bridge Skill

This skill provides a robust method for syncing local files to an Azure Blob Storage container using `az storage blob upload-batch`. It is designed to handle network instability with retry logic and can monitor a directory for new files.

## Prerequisites

1.  **Azure CLI (`az`)**: Must be installed and authenticated (`az login`).
2.  **Bash Environment**: Requires Git Bash, WSL, or a Linux/Mac environment. (PowerShell equivalent provided in `scripts/`).

## Usage

### 1. One-time Sync

To sync a directory once:

```bash
./scripts/sync_to_azure.sh --source "/path/to/local/folder" --container "Thor_Backups"
```

### 2. Continuous Monitor (Watcher)

To continuously watch a folder and sync when changes are detected:

```bash
./scripts/sync_to_azure.sh --source "/path/to/local/folder" --container "Thor_Backups" --watch
```

## Configuration

*   **Retry Attempts**: Default 5.
*   **Retry Delay**: Exponential backoff starting at 2 seconds.
*   **Connection String**: Uses `AZUREWEBJOBSSTORAGE` environment variable if set, otherwise falls back to `az` CLI authentication context.
