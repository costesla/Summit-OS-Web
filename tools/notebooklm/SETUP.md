# NotebookLM Agent Tool Integration

This module provides an agentic tool wrapper for Google NotebookLM, allowing programmatic notebook creation, source addition, and querying. 

## Route Choice & Maintenance Note
**Route Chosen**: Unofficial `notebooklm-py` library (Route 2). 

**Maintenance Note**: This integration uses unofficial endpoints which Google may change without notice. If the endpoints break, the `NotebookLMTool` is designed to fail loudly with a `NotebookLMUpstreamError` rather than returning malformed garbage. Please note that this drives your personal Google account. **Keep call volume at human-scale (no automated loops or scheduled cron jobs) to avoid violating Terms of Service or getting your account flagged.**

## Authentication Setup

This tool uses a cookie-based authentication model to access your personal NotebookLM account. 

### 1. Extracting the Session Token
You need to authenticate `notebooklm-py` by extracting your browser cookies:
1. Open a terminal and navigate to `tools/notebooklm`.
2. Initialize a local virtual environment: `python -m venv venv`
3. Activate it and install dependencies: `pip install -r requirements.txt`
4. Run the login command: `notebooklm login --browser-cookies chrome`
   *This will extract the session token and store it locally for the library to use.*

### 2. Environment Variables
If you are deploying this wrapper to another MCP server or Copilot Studio in the future, you may need to export the session tokens manually.
Create a `.env` file in the `tools/notebooklm/` directory (e.g., `tools/notebooklm/.env`) and store any necessary configuration (e.g., `NOTEBOOKLM_SESSION_TOKEN=your_token_here`).

> [!WARNING]
> **Pre-Zip Validation Gate**: The `tools/notebooklm/.env` file is explicitly ignored in the repository's `.gitignore`. Additionally, because this entire module lives in `tools/notebooklm/` (at the repository root) rather than `backend/`, it falls entirely outside the `create_backend_zip.py` blast radius. Your tokens will **not** be zipped or deployed to Azure Functions.

### 3. Token Refresh Procedure
Google session cookies expire periodically. If you start seeing authentication errors:

* **Error Signature**: The `NotebookLMTool` will raise a `NotebookLMAuthError` (e.g., "Session expired or auth failed"). This is distinct from an upstream breakage error.
* **Fix**: You must re-extract your cookies. 
  1. Open Chrome and ensure you are logged into NotebookLM.
  2. Re-run `notebooklm login --browser-cookies chrome` in the `tools/notebooklm` directory.
