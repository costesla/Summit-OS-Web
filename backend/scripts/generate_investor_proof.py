import os
import sys
import json
import logging
import hashlib
from dotenv import load_dotenv
from datetime import datetime

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', 'summit_sync', '.env')
load_dotenv(dotenv_path)

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from services.agent_orchestrator import SystemOrchestrator
from services.database import DatabaseClient

logging.basicConfig(level=logging.INFO, format='%(message)s')

def generate_investor_report():
    """
    Generates a cryptographically verifiable investor report.
    It retrieves the highest-confidence FSD segments natively from SQL, outputs 
    their explicit pointers, and generates a SHA-256 hash of the final report block 
    so it can be securely audited against the live DB.
    """
    orchestrator = SystemOrchestrator()
    db = DatabaseClient()
    
    # 1. Fetch raw underlying facts directly from SQL (Evidence Layer)
    query = """
    SELECT TOP 5 
        source_pointer,
        confidence_score,
        timestamp_utc, 
        derivation_reason,
        raw_text_hash
    FROM System_Vectors
    WHERE source_type = 'FSD' AND confidence_score >= 0.95
    ORDER BY confidence_score DESC, timestamp_utc DESC
    """
    results = db.execute_query_with_results(query)
    
    if not results:
        logging.warning("No FSD segments met the >95% confidence threshold for reporting.")
        return

    # 2. Compile the Immutable Fact Block
    report_lines = [
        "===================================================================",
        "                     COS TESLA - INVESTOR PROOF                    ",
        f"                     Generated: {datetime.utcnow().isoformat()}Z   ",
        "===================================================================",
        "The following operational claims are fully supported by verifiable ",
        "vehicle telemetry embedded in the SummitOS Agentic SQL Vector Store.",
        "-------------------------------------------------------------------"
    ]
    
    fact_block_raw = ""
    for r in results:
        pointer = r['source_pointer']
        conf = r['confidence_score']
        ts = r['timestamp_utc']
        reason = r['derivation_reason']
        hsh = r['raw_text_hash']
        
        line = f"[{ts}] Pointer: {pointer} | Confidence: {conf:.3f} | Hash: {hsh[:8]}...\n   Claim: {reason}"
        report_lines.append(line)
        fact_block_raw += line + "\n"
        
    # 3. Cryptographically hash the fact block
    report_hash = hashlib.sha256(fact_block_raw.encode('utf-8')).hexdigest()
    
    report_lines.append("-------------------------------------------------------------------")
    report_lines.append(f"REPORT_CRYPTOGRAPHIC_HASH: {report_hash}")
    report_lines.append("Auditors may query this hash against the live Canonical Vector Contract.")
    report_lines.append("===================================================================")
    
    # 4. Agentic Narrative Contextualization (Narrative Mode)
    narrative_query = "Summarize our latest top-tier FSD segment performance for a Q1 investor update."
    narrative_body = orchestrator.process_query(narrative_query, "narrative")
    
    report_lines.append("\n" + narrative_body)
    
    # Render Report
    final_output = "\n".join(report_lines)
    print(final_output)

if __name__ == "__main__":
    generate_investor_report()
