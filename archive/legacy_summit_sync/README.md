# Summit Sync

**Summit Sync** is the cloud-native replacement for the legacy "MobilityOS" scripts. 
It is a serverless Azure Function that automates the ingestion, processing, and storage of business data.

## Architecture
1.  **Trigger**: New file uploaded to `stsummitosprod/uploads`.
2.  **Processor**: Python Azure Function (Event Grid Trigger).
3.  **Intelligence**: Azure AI Vision (OCR).
4.  **Enrichment**: Tessie API (Telematics).
5.  **Storage**: Azure SQL Database (`sql-summitos-core`).

## Directory Structure
*   `function_app.py`: Main logic entry point.
*   `requirements.txt`: Python dependencies.
*   `lib/`: Helper modules (OCR, Tessie, Database).
