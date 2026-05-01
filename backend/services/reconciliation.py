import logging
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional
from .database import DatabaseClient
from .semantic_ingestion import SemanticIngestionService

log = logging.getLogger(__name__)

# ─── Merchant Entity Resolution Map ──────────────────────────────────────────
# Maps abbreviations/fragments to full legal business names and categories.
MERCHANT_ENTITY_MAP = {
    # Food & Beverage
    "sbux": ("Starbucks Corporation", "Food & Beverage"),
    "starbucks": ("Starbucks Corporation", "Food & Beverage"),
    "mcd": ("McDonald's Corporation", "Food & Beverage"),
    "mcdonalds": ("McDonald's Corporation", "Food & Beverage"),
    "mcdonald": ("McDonald's Corporation", "Food & Beverage"),
    "chick-fil-a": ("Chick-fil-A Inc.", "Food & Beverage"),
    "chickfila": ("Chick-fil-A Inc.", "Food & Beverage"),
    "cfa": ("Chick-fil-A Inc.", "Food & Beverage"),
    "chipotle": ("Chipotle Mexican Grill Inc.", "Food & Beverage"),
    "cmg": ("Chipotle Mexican Grill Inc.", "Food & Beverage"),
    "taco bell": ("Taco Bell Corp.", "Food & Beverage"),
    "tacobell": ("Taco Bell Corp.", "Food & Beverage"),
    "domino": ("Domino's Pizza Inc.", "Food & Beverage"),
    "dunkin": ("Dunkin' Brands Group Inc.", "Food & Beverage"),
    "panera": ("Panera Bread Company", "Food & Beverage"),
    "wendys": ("Wendy's Company", "Food & Beverage"),
    "subway": ("Subway IP LLC", "Food & Beverage"),
    "wingstop": ("Wingstop Inc.", "Food & Beverage"),
    "dutch bros": ("Dutch Bros Inc.", "Food & Beverage"),
    "dutch": ("Dutch Bros Inc.", "Food & Beverage"),

    # Fuel & Charging
    "tesla supercharger": ("Tesla Inc. – Supercharger", "EV Charging"),
    "tesla charging": ("Tesla Inc. – Supercharger", "EV Charging"),
    "supercharger": ("Tesla Inc. – Supercharger", "EV Charging"),
    "blink": ("Blink Charging Co.", "EV Charging"),
    "chargepoint": ("ChargePoint Holdings Inc.", "EV Charging"),
    "evgo": ("EVgo Inc.", "EV Charging"),
    "circle k": ("Circle K Stores Inc.", "Fuel"),
    "circlek": ("Circle K Stores Inc.", "Fuel"),
    "chevron": ("Chevron Corporation", "Fuel"),
    "shell": ("Shell plc", "Fuel"),
    "exxon": ("ExxonMobil Corporation", "Fuel"),
    "mobil": ("ExxonMobil Corporation", "Fuel"),
    "bp": ("BP p.l.c.", "Fuel"),
    "sinclair": ("Sinclair Oil Corporation", "Fuel"),

    # Retail & General
    "walmart": ("Walmart Inc.", "Retail"),
    "wmt": ("Walmart Inc.", "Retail"),
    "target": ("Target Corporation", "Retail"),
    "amzn": ("Amazon.com Inc.", "Online Retail"),
    "amazon": ("Amazon.com Inc.", "Online Retail"),
    "costco": ("Costco Wholesale Corporation", "Retail"),
    "sam's": ("Sam's Club (Walmart Inc.)", "Retail"),

    # Rideshare & Transport
    "uber": ("Uber Technologies Inc.", "Rideshare Income"),
    "lyft": ("Lyft Inc.", "Rideshare Income"),

    # Tesla / Vehicle
    "tsla": ("Tesla Inc.", "Vehicle Services"),
    "tesla": ("Tesla Inc.", "Vehicle Services"),
    "tesla service": ("Tesla Inc. – Service Center", "Vehicle Maintenance"),

    # Banking & Finance
    "chase": ("JPMorgan Chase Bank N.A.", "Banking"),
    "paypal": ("PayPal Holdings Inc.", "Finance"),
    "venmo": ("Venmo (PayPal Holdings Inc.)", "Finance"),
    "zelle": ("Zelle (Early Warning Services LLC)", "Finance"),

    # Insurance
    "geico": ("GEICO Corporation", "Insurance"),
    "progressive": ("Progressive Corporation", "Insurance"),
    "state farm": ("State Farm Mutual Automobile Insurance", "Insurance"),

    # Telecom
    "at&t": ("AT&T Inc.", "Telecommunications"),
    "att": ("AT&T Inc.", "Telecommunications"),
    "t-mobile": ("T-Mobile US Inc.", "Telecommunications"),
    "tmobile": ("T-Mobile US Inc.", "Telecommunications"),
    "verizon": ("Verizon Communications Inc.", "Telecommunications"),
}


def resolve_merchant(raw_name: str) -> tuple[str, str]:
    """
    Maps a raw merchant name/abbreviation to its full legal name and category.
    Returns (resolved_name, category).
    """
    if not raw_name:
        return ("Unknown Merchant", "Uncategorized")
    
    lower = raw_name.strip().lower()
    
    # Exact match first
    if lower in MERCHANT_ENTITY_MAP:
        return MERCHANT_ENTITY_MAP[lower]
    
    # Partial / contains match
    for key, (name, cat) in MERCHANT_ENTITY_MAP.items():
        if key in lower or lower in key:
            return (name, cat)
    
    # Fallback: title-case the raw name
    return (raw_name.strip().title(), "General Business")


# ─── Reconciliation Service ───────────────────────────────────────────────────

class ReconciliationService:
    """
    Financial reconciliation engine for SummitOS.
    
    Cross-references OneDrive OCR receipts with Chase/Teller bank transactions,
    writes structured records to Rides.Reconciliation_Ledger, and creates
    vector embeddings for semantic querying.
    
    Follows the spec:
    - Merchant entity resolution (abbreviation → full legal name)
    - +3 day bank posting window matching
    - Match confidence scoring (0–100%)
    - Dual injection: SQL ledger + vector memory
    - Flags fuzzy matches (>$0.01 delta) for manual review
    """

    POSTING_WINDOW_DAYS = 3
    FUZZY_THRESHOLD = 0.01

    def __init__(self):
        self.db = DatabaseClient()
        self.semantic = SemanticIngestionService()
        self._ensure_ledger_table()

    def _ensure_ledger_table(self):
        """Creates Rides.Reconciliation_Ledger if it doesn't exist."""
        conn = self.db.get_connection()
        if not conn:
            return
        cursor = conn.cursor()
        try:
            cursor.execute("""
                IF OBJECT_ID('Rides.Reconciliation_Ledger', 'U') IS NULL
                CREATE TABLE Rides.Reconciliation_Ledger (
                    RecordID         NVARCHAR(100) PRIMARY KEY,
                    MerchantName     NVARCHAR(255),
                    TransactionDate  DATE,
                    TotalAmount      DECIMAL(10,2),
                    Currency         NVARCHAR(10) DEFAULT 'USD',
                    ChaseReferenceID NVARCHAR(255) NULL,
                    MatchConfidence  INT NULL,
                    Category         NVARCHAR(100),
                    Reconciled       BIT DEFAULT 0,
                    RequiresReview   BIT DEFAULT 0,
                    ReviewReason     NVARCHAR(500) NULL,
                    SourceFile       NVARCHAR(500) NULL,
                    RawOCRText       NVARCHAR(MAX) NULL,
                    EmbeddingText    NVARCHAR(MAX) NULL,
                    CreatedAt        DATETIME DEFAULT GETDATE(),
                    LastUpdated      DATETIME DEFAULT GETDATE()
                )
            """)
            conn.commit()
        except Exception as e:
            log.error(f"Ledger table creation error: {e}")
        finally:
            conn.close()

    # ─── Public Entry Point ──────────────────────────────────────────────────

    def reconcile_receipt(
        self,
        ocr_text: str,
        source_filename: str,
        parsed_amount: Optional[float] = None,
        parsed_date: Optional[str] = None,
        parsed_merchant: Optional[str] = None,
        vehicle_ref: str = "Thor"
    ) -> dict:
        """
        Main reconciliation pipeline for a single receipt.
        
        Args:
            ocr_text: Raw OCR text from Azure Document Intelligence / Vision
            source_filename: Name of the OneDrive file (for audit trail)
            parsed_amount: Override if caller already extracted the total
            parsed_date: Override if caller already extracted the date (YYYY-MM-DD)
            parsed_merchant: Override if caller already extracted the merchant
            vehicle_ref: Vehicle context label (default: "Thor")
        
        Returns:
            Full reconciliation record matching the spec output format.
        """
        logs = []

        # 1. Parse OCR if fields not provided
        merchant_raw = parsed_merchant or self._extract_merchant(ocr_text)
        total = parsed_amount or self._extract_total(ocr_text)
        date_str = parsed_date or self._extract_date(ocr_text)

        logs.append(f"OCR Parsed: merchant='{merchant_raw}', total=${total:.2f}, date={date_str}")

        # 2. Entity Resolution
        merchant_full, category = resolve_merchant(merchant_raw)
        logs.append(f"Resolved: '{merchant_raw}' → '{merchant_full}' ({category})")

        # 3. Match against bank feed (Teller/Chase transactions)
        bank_match = self._find_bank_match(total, date_str)
        chase_ref = bank_match.get("id") if bank_match else None
        bank_amount = float(bank_match.get("amount", 0)) if bank_match else None

        # 4. Confidence scoring
        confidence, reconciled, requires_review, review_reason = self._score_match(
            total, bank_amount, chase_ref, merchant_raw
        )

        logs.append(
            f"Bank Match: chase_id={chase_ref}, confidence={confidence}%, "
            f"reconciled={reconciled}, review={requires_review}"
        )
        if review_reason:
            logs.append(f"Review Reason: {review_reason}")

        # 5. Build embedding text for vector memory
        embedding_text = self._build_embedding_text(
            merchant_full, category, total, date_str,
            chase_ref, vehicle_ref, review_reason
        )

        # 6. Build the unique record ID
        id_seed = f"{source_filename}-{date_str}-{total}"
        record_id = f"REC-{hashlib.sha256(id_seed.encode()).hexdigest()[:12].upper()}"

        # 7. SQL write → Rides.Reconciliation_Ledger
        self._write_to_ledger(
            record_id=record_id,
            merchant_name=merchant_full,
            transaction_date=date_str,
            total=total,
            chase_ref=chase_ref,
            confidence=confidence,
            category=category,
            reconciled=reconciled,
            requires_review=requires_review,
            review_reason=review_reason,
            source_file=source_filename,
            raw_ocr=ocr_text,
            embedding_text=embedding_text
        )

        # 8. Vector write → Semantic Memory
        self._write_to_vector(record_id, embedding_text, date_str, source_filename, vehicle_ref)

        # 9. Return structured output matching the spec
        return {
            "sql_ledger": {
                "table": "Reconciliation_Ledger",
                "data": {
                    "merchant_name": merchant_full,
                    "transaction_date": date_str,
                    "total_amount": round(total, 2),
                    "currency": "USD",
                    "chase_reference_id": chase_ref,
                    "match_confidence": f"{confidence}%",
                    "category": category
                }
            },
            "vector_memory": {
                "embedding_text": embedding_text,
                "metadata": {
                    "source": "OneDrive_Upload",
                    "system": "SummitOS_v3",
                    "vehicle_ref": vehicle_ref
                }
            },
            "status_report": {
                "reconciled": reconciled,
                "requires_manual_review": requires_review,
                "review_reason": review_reason
            },
            "_internal": {
                "record_id": record_id,
                "logs": logs
            }
        }

    def reconcile_batch(self, receipts: list, vehicle_ref: str = "Thor") -> dict:
        """
        Reconcile a list of receipts in one call.
        Each item: { ocr_text, source_filename, parsed_amount?, parsed_date?, parsed_merchant? }
        """
        results = []
        reconciled_count = 0
        review_count = 0

        for r in receipts:
            result = self.reconcile_receipt(
                ocr_text=r.get("ocr_text", ""),
                source_filename=r.get("source_filename", "unknown"),
                parsed_amount=r.get("parsed_amount"),
                parsed_date=r.get("parsed_date"),
                parsed_merchant=r.get("parsed_merchant"),
                vehicle_ref=vehicle_ref
            )
            results.append(result)
            if result["status_report"]["reconciled"]:
                reconciled_count += 1
            if result["status_report"]["requires_manual_review"]:
                review_count += 1

        return {
            "success": True,
            "total": len(results),
            "reconciled": reconciled_count,
            "requires_review": review_count,
            "records": results
        }

    # ─── OCR Extraction Helpers ──────────────────────────────────────────────

    def _extract_total(self, text: str) -> float:
        """Extracts the total dollar amount from raw OCR text."""
        import re
        # Priority order: Total > Grand Total > Amount Due > last dollar amount
        patterns = [
            r"(?:grand\s+)?total[\s:*]*\$?([\d,]+\.\d{2})",
            r"amount\s+due[\s:*]*\$?([\d,]+\.\d{2})",
            r"balance\s+due[\s:*]*\$?([\d,]+\.\d{2})",
            r"\$\s*([\d,]+\.\d{2})",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return float(m.group(1).replace(",", ""))
        return 0.0

    def _extract_date(self, text: str) -> str:
        """Extracts the transaction date from raw OCR text."""
        import re
        patterns = [
            r"(\d{4}-\d{2}-\d{2})",                          # 2026-04-29
            r"(\d{1,2}/\d{1,2}/\d{4})",                      # 4/29/2026
            r"(\d{1,2}/\d{1,2}/\d{2})",                      # 4/29/26
            r"(\w+ \d{1,2},?\s*\d{4})",                      # April 29, 2026
        ]
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                raw = m.group(1)
                # Normalize to YYYY-MM-DD
                for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%B %d %Y", "%B %d, %Y"):
                    try:
                        return datetime.strptime(raw.replace(",", ""), fmt).strftime("%Y-%m-%d")
                    except ValueError:
                        continue
        return datetime.now().strftime("%Y-%m-%d")

    def _extract_merchant(self, text: str) -> str:
        """Extracts the merchant name from the first non-empty line of the OCR text."""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        # The merchant name is usually the first 1-2 lines
        return lines[0] if lines else "Unknown"

    # ─── Bank Matching ───────────────────────────────────────────────────────

    def _find_bank_match(self, amount: float, date_str: str) -> Optional[dict]:
        """
        Searches Teller transactions in SQL for a matching amount within the
        +3 day posting window. Returns the best match or None.
        """
        if not date_str or amount == 0:
            return None

        try:
            receipt_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return None

        window_start = (receipt_date - timedelta(days=1)).strftime("%Y-%m-%d")
        window_end   = (receipt_date + timedelta(days=self.POSTING_WINDOW_DAYS)).strftime("%Y-%m-%d")

        query = """
            SELECT TOP 5
                ExpenseID AS id,
                Amount    AS amount,
                Note      AS description,
                Timestamp AS transaction_date,
                Category  AS category
            FROM Rides.ManualExpenses
            WHERE Timestamp >= CAST(? AS DATE)
              AND Timestamp <= CAST(? AS DATE)
              AND ABS(Amount - ?) < 1.00
            ORDER BY ABS(Amount - ?) ASC, ABS(DATEDIFF(day, Timestamp, ?)) ASC
        """
        try:
            results = self.db.execute_query_params(
                query,
                (window_start, window_end, amount, amount, receipt_date)
            )
            if results:
                return results[0]
        except Exception as e:
            log.error(f"Bank match query error: {e}")

        return None

    # ─── Confidence Scoring ──────────────────────────────────────────────────

    def _score_match(
        self,
        ocr_amount: float,
        bank_amount: Optional[float],
        chase_ref: Optional[str],
        merchant_raw: str
    ) -> tuple[int, bool, bool, Optional[str]]:
        """
        Returns (confidence %, reconciled, requires_review, review_reason).
        
        Scoring logic:
        - No bank match found:          0%, not reconciled, review required
        - Amount delta > $0.01:        50%, not reconciled, flagged as Fuzzy Match
        - Exact amount match:          80%, reconciled
        - Exact + known merchant:     100%, reconciled
        """
        if not chase_ref or bank_amount is None:
            return (0, False, True, "No matching bank transaction found within +3 day posting window.")

        delta = abs(ocr_amount - abs(bank_amount))

        if delta > self.FUZZY_THRESHOLD:
            reason = (
                f"Fuzzy Match: OCR total ${ocr_amount:.2f} differs from "
                f"bank amount ${abs(bank_amount):.2f} by ${delta:.2f}."
            )
            return (50, False, True, reason)

        # Exact match — boost confidence if merchant is resolvable
        _, category = resolve_merchant(merchant_raw)
        confidence = 100 if category != "General Business" else 80

        return (confidence, True, False, None)

    # ─── Embedding Text Builder ──────────────────────────────────────────────

    def _build_embedding_text(
        self,
        merchant: str,
        category: str,
        total: float,
        date_str: str,
        chase_ref: Optional[str],
        vehicle_ref: str,
        review_reason: Optional[str]
    ) -> str:
        match_clause = (
            f"Match confirmed via Chase transaction ID {chase_ref}."
            if chase_ref
            else "No bank match found; manual review required."
        )
        review_clause = f" Note: {review_reason}" if review_reason else ""
        return (
            f"Purchased at {merchant} ({category}) on {date_str} for a total of ${total:.2f} USD. "
            f"{match_clause} "
            f"Business context: operational expense for COS Tesla – Executive Transport fleet vehicle '{vehicle_ref}'."
            f"{review_clause}"
        )

    # ─── SQL Write ───────────────────────────────────────────────────────────

    def _write_to_ledger(self, **kwargs):
        conn = self.db.get_connection()
        if not conn:
            return
        cursor = conn.cursor()
        try:
            cursor.execute("""
                MERGE INTO Rides.Reconciliation_Ledger AS target
                USING (SELECT ? AS RecordID) AS source
                ON (target.RecordID = source.RecordID)
                WHEN MATCHED THEN
                    UPDATE SET
                        MerchantName     = ?,
                        TransactionDate  = ?,
                        TotalAmount      = ?,
                        ChaseReferenceID = ?,
                        MatchConfidence  = ?,
                        Category         = ?,
                        Reconciled       = ?,
                        RequiresReview   = ?,
                        ReviewReason     = ?,
                        SourceFile       = ?,
                        RawOCRText       = ?,
                        EmbeddingText    = ?,
                        LastUpdated      = GETDATE()
                WHEN NOT MATCHED THEN
                    INSERT (
                        RecordID, MerchantName, TransactionDate, TotalAmount,
                        ChaseReferenceID, MatchConfidence, Category,
                        Reconciled, RequiresReview, ReviewReason,
                        SourceFile, RawOCRText, EmbeddingText
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                # MERGE key
                kwargs["record_id"],
                # UPDATE SET
                kwargs["merchant_name"], kwargs["transaction_date"], kwargs["total"],
                kwargs["chase_ref"], kwargs["confidence"], kwargs["category"],
                1 if kwargs["reconciled"] else 0,
                1 if kwargs["requires_review"] else 0,
                kwargs["review_reason"],
                kwargs["source_file"], kwargs["raw_ocr"], kwargs["embedding_text"],
                # INSERT values
                kwargs["record_id"],
                kwargs["merchant_name"], kwargs["transaction_date"], kwargs["total"],
                kwargs["chase_ref"], kwargs["confidence"], kwargs["category"],
                1 if kwargs["reconciled"] else 0,
                1 if kwargs["requires_review"] else 0,
                kwargs["review_reason"],
                kwargs["source_file"], kwargs["raw_ocr"], kwargs["embedding_text"]
            ))
            conn.commit()
            log.info(f"Ledger record written: {kwargs['record_id']}")
        except Exception as e:
            log.error(f"Ledger write error: {e}")
        finally:
            conn.close()

    # ─── Vector Write ────────────────────────────────────────────────────────

    def _write_to_vector(
        self, record_id: str, embedding_text: str,
        date_str: str, source_file: str, vehicle_ref: str
    ):
        try:
            raw_hash = hashlib.sha256(embedding_text.encode()).hexdigest()
            dt = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.utcnow()

            vector_data = {
                "vector_id": f"V-{record_id}",
                "source_type": "Reconciliation",
                "timestamp_utc": dt,
                "raw_text_hash": raw_hash,
                "source_pointer": source_file,
                "derivation_reason": embedding_text
            }
            self.semantic.vector_store.add_vector(vector_data)
            log.info(f"Vector written for {record_id}")
        except Exception as e:
            log.error(f"Vector write error for {record_id}: {e}")
