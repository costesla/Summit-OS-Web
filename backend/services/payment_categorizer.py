"""Payee classification for the SummitOS Payment Tracker.

Pure functions only (no DB/network access) so this module is directly
unit-testable. Transaction amounts follow the Teller sign convention:
negative = money out, positive = money in.
"""

from __future__ import annotations

import datetime

BUSINESS_ACCOUNT = "9776"
PERSONAL_ACCOUNT = "2085"

# The arrangement itself began 2026-04-20, but Peter chose to start tier/
# balance tracking fresh from July 2026 — earlier months are settled history.
LUIS_START_DATE = datetime.date(2026, 7, 1)
LUIS_FULL_AMOUNT = 190.00
LUIS_ROUGH_AMOUNT = 130.00
LUIS_ROUGH_DEFERRED = 60.00

FORMER_CLIENTS = ("esmeralda", "terrance")
# Jacquelyn Heslep was flagged as a former client while she was on a deferred
# billing arrangement; that arrangement ended and she's a normal paying
# client now, same as anyone else — no longer excluded from revenue.

EMERSON_KEYWORD = "emerson"
EMERSON_OFF_WEEKDAYS = {2, 3}  # Monday=0 ... Wednesday=2, Thursday=3

# Categories whose transactions represent a monthly fixed obligation
# (used to set Payments.RecurringFlag).
RECURRING_CATEGORIES = {
    "Vehicle Services", "Internet", "Telecommunications", "SaaS", "Car Wash",
    "Cloud Storage", "Bank Fee", "Streaming", "Media", "Domain",
    "Family Obligation",
}

# Ordered (pattern, category, subcategory, direction) rules — first match wins.
# direction is None when it should be inferred from the transaction's own sign.
PAYEE_RULES: list[tuple[str, str, str | None, str | None]] = [
    # Business revenue — inbound
    ("uber san francisco", "Uber Revenue", "Card Deposit", "inbound"),
    ("rasier", "Uber Revenue", "ACH Deposit", "inbound"),
    ("raiser", "Uber Revenue", "ACH Deposit", "inbound"),
    ("uber san francis", "Uber Revenue", "Card Deposit", "inbound"),
    ("stripe", "Booking Revenue", "costesla.com", "inbound"),
    # Zelle-based rules match on the person's name only, not "Zelle From/To X"
    # verbatim — Teller's real description format is "Zelle payment from/to X",
    # and can truncate long names, so an exact phrase match silently misses them.
    ("emerson", "Private Client Revenue", "Emerson Jean Baptiste", "inbound"),
    ("madelyn", "Private Client Revenue", "Berezov Family", "inbound"),
    ("danny kennedy", "Tip/Fare", None, "inbound"),

    # Fixed obligations — outbound
    ("luis canales", "Vehicle Financing", "Luis Canales", "outbound"),
    ("tesla supercharger", "EV Charging", None, "outbound"),
    ("tesla subscription", "Vehicle Services", "Tesla Subscription", "outbound"),
    ("quantum fiber", "Internet", None, "outbound"),
    ("t-mobile", "Telecommunications", None, "outbound"),
    ("tmobile", "Telecommunications", None, "outbound"),
    ("microsoft", "SaaS", "Microsoft", "outbound"),
    ("claude.ai", "SaaS", "Claude.ai", "outbound"),
    ("anthropic", "SaaS", "Claude.ai", "outbound"),
    ("tessie", "Vehicle Services", "Tessie", "outbound"),
    ("weatherwise", "SaaS", "WeatherWise", "outbound"),
    ("quick quack", "Car Wash", None, "outbound"),
    ("quickquack", "Car Wash", None, "outbound"),
    ("google one", "Cloud Storage", None, "outbound"),
    ("chase msf", "Bank Fee", "Chase MSF", "outbound"),
    ("monthly service fee", "Bank Fee", "Chase MSF", "outbound"),

    # Personal — outbound (flagged for exclusion from business metrics)
    ("netflix", "Streaming", None, "outbound"),
    ("peacock", "Streaming", None, "outbound"),
    ("hbo max", "Streaming", None, "outbound"),
    ("hbomax", "Streaming", None, "outbound"),
    ("disney", "Streaming", None, "outbound"),
    ("fubo", "Streaming", None, "outbound"),
    ("walmart+", "Streaming", None, "outbound"),
    ("amazon prime", "Streaming", None, "outbound"),
    ("audible", "Media", None, "outbound"),
    ("patreon", "Media", None, "outbound"),
    ("wapo", "Media", None, "outbound"),
    ("washington post", "Media", None, "outbound"),
    ("godaddy", "Domain", None, "outbound"),

    # Food & dining — outbound
    ("starbucks", "Food & Dining", None, "outbound"),
    ("mcdonald", "Food & Dining", None, "outbound"),
    ("taco bell", "Food & Dining", None, "outbound"),
    ("wendy", "Food & Dining", None, "outbound"),
    ("whataburger", "Food & Dining", None, "outbound"),
    ("dutch bros", "Food & Dining", None, "outbound"),
    ("culver", "Food & Dining", None, "outbound"),
    ("fazoli", "Food & Dining", None, "outbound"),
    ("subway", "Food & Dining", None, "outbound"),

    # Personal habits / family — outbound
    ("red star vapor", "Personal Habit", "Vapor", "outbound"),
    ("cash app*magen burrous", "Family Obligation", "Magen Burrous", "outbound"),
    ("cash app*carl ferrell", "Family Obligation", "Carl Ferrell", "outbound"),
]


def is_former_client(text: str) -> bool:
    return any(name in text for name in FORMER_CLIENTS)


def categorize_payee(counterparty: str, amount: float, account: str) -> dict:
    """Classify a single transaction by counterparty text and signed amount."""
    text = (counterparty or "").lower()
    direction = "inbound" if amount > 0 else "outbound"

    if is_former_client(text):
        return {
            "category": "Flagged",
            "subcategory": "Former Client",
            "direction": direction,
            "recurring_flag": False,
            "anomaly_flag": True,
            "anomaly_reason": f"Inbound from former client ({counterparty}) — do not auto-credit",
        }

    if amount > 0 and "atm" in text and ("deposit" in text or "cash" in text):
        return {
            "category": "Cash Deposit",
            "subcategory": None,
            "direction": "inbound",
            "recurring_flag": False,
            "anomaly_flag": True,
            "anomaly_reason": "ATM cash deposit — source needs manual log",
        }

    for pattern, category, subcategory, rule_direction in PAYEE_RULES:
        if pattern in text:
            return {
                "category": category,
                "subcategory": subcategory,
                "direction": rule_direction or direction,
                "recurring_flag": category in RECURRING_CATEGORIES,
                "anomaly_flag": False,
                "anomaly_reason": None,
            }

    return {
        "category": "Uncategorized",
        "subcategory": None,
        "direction": direction,
        "recurring_flag": False,
        "anomaly_flag": False,
        "anomaly_reason": None,
    }


def _to_cents(amount: float) -> int:
    return int(round(float(amount) * 100))


def classify_luis_payment(amount_sent: float, prior_balance: float, payment_date) -> dict:
    """Applies the three-tier (five-state) Luis Canales financing logic.

    Returns: tier, deferred_amount, new_balance, anomaly_flag, anomaly_reason.
    A $130 payment is a valid "Rough" day, not an error. Amounts strictly
    between $130 and $190 are held for manual review rather than
    auto-categorized. Only applies on/after LUIS_START_DATE.
    """
    if isinstance(payment_date, str):
        payment_date = datetime.date.fromisoformat(payment_date)

    if payment_date < LUIS_START_DATE:
        return {
            "tier": "Pre-Arrangement",
            "deferred_amount": 0.0,
            "new_balance": round(prior_balance, 2),
            "anomaly_flag": False,
            "anomaly_reason": None,
        }

    amount_cents = _to_cents(amount_sent)
    full_cents = _to_cents(LUIS_FULL_AMOUNT)
    rough_cents = _to_cents(LUIS_ROUGH_AMOUNT)

    if amount_cents <= 0:
        return {
            "tier": "Missed",
            "deferred_amount": LUIS_FULL_AMOUNT,
            "new_balance": round(prior_balance + LUIS_FULL_AMOUNT, 2),
            "anomaly_flag": True,
            "anomaly_reason": "No Luis Canales payment sent today",
        }

    if amount_cents < rough_cents:
        return {
            "tier": "Underpayment",
            "deferred_amount": LUIS_FULL_AMOUNT,
            "new_balance": round(prior_balance + LUIS_FULL_AMOUNT, 2),
            "anomaly_flag": True,
            "anomaly_reason": f"Underpayment: ${amount_sent:.2f} sent (below $130 rough-day minimum)",
        }

    if amount_cents == rough_cents:
        return {
            "tier": "Rough",
            "deferred_amount": LUIS_ROUGH_DEFERRED,
            "new_balance": round(prior_balance + LUIS_ROUGH_DEFERRED, 2),
            "anomaly_flag": False,
            "anomaly_reason": None,
        }

    if amount_cents < full_cents:
        return {
            "tier": "Review",
            "deferred_amount": 0.0,
            "new_balance": round(prior_balance, 2),
            "anomaly_flag": True,
            "anomaly_reason": f"${amount_sent:.2f} sent — between rough-day minimum and full payment, needs manual review",
        }

    # Full day. Any amount over $190 pays down the existing running balance.
    overage = round(amount_sent - LUIS_FULL_AMOUNT, 2)
    new_balance = round(max(prior_balance - overage, 0.0), 2)
    return {
        "tier": "Full",
        "deferred_amount": 0.0,
        "new_balance": new_balance,
        "anomaly_flag": False,
        "anomaly_reason": None,
    }


def check_consecutive_missed(previous_tiers_most_recent_first: list[str]) -> str | None:
    """Given today's tier is already 'Missed', checks whether prior days were
    also missed and returns an escalation reason once 2+ consecutive days
    (today + at least one prior day) are missed."""
    consecutive_prior = 0
    for tier in previous_tiers_most_recent_first:
        if tier == "Missed":
            consecutive_prior += 1
        else:
            break
    if consecutive_prior >= 1:
        return f"Escalated: {consecutive_prior + 1} consecutive missed Luis Canales payments"
    return None


def should_flag_missing_emerson(check_date, had_payment: bool) -> str | None:
    """Emerson is off Wednesday/Thursday — never flag missing income those days."""
    if isinstance(check_date, str):
        check_date = datetime.date.fromisoformat(check_date)
    if had_payment or check_date.weekday() in EMERSON_OFF_WEEKDAYS:
        return None
    return "No private client (Emerson) payment recorded for an expected work day"


def find_transfer_pairs(transactions: list[dict]) -> set:
    """Identifies inter-account transfers and Cash App/Venmo passthrough that
    must be excluded from revenue/expense totals.

    Each transaction dict needs: id, account ('9776'/'2085'), amount (signed),
    date (datetime.date), counterparty (str, optional).

    Matches same-day, equal-magnitude, opposite-sign pairs between the 9776
    and 2085 accounts, and Cash App/Venmo inbound-to-2085 matched to a
    same-day outbound-to-9776 of the same amount.
    """
    transfer_ids: set = set()
    n = len(transactions)
    for i in range(n):
        a = transactions[i]
        if a["id"] in transfer_ids:
            continue
        for j in range(i + 1, n):
            b = transactions[j]
            if b["id"] in transfer_ids:
                continue
            if a["date"] != b["date"]:
                continue
            if round(abs(a["amount"]), 2) != round(abs(b["amount"]), 2):
                continue
            if (a["amount"] > 0) == (b["amount"] > 0):
                continue  # must be opposite direction

            accounts = {a["account"], b["account"]}
            is_cross_account_transfer = accounts == {BUSINESS_ACCOUNT, PERSONAL_ACCOUNT}

            a_text = (a.get("counterparty") or "").lower()
            b_text = (b.get("counterparty") or "").lower()
            is_passthrough = (
                a["account"] == PERSONAL_ACCOUNT and b["account"] == BUSINESS_ACCOUNT
                and ("cash app" in a_text or "venmo" in a_text)
            ) or (
                b["account"] == PERSONAL_ACCOUNT and a["account"] == BUSINESS_ACCOUNT
                and ("cash app" in b_text or "venmo" in b_text)
            )

            if is_cross_account_transfer or is_passthrough:
                transfer_ids.add(a["id"])
                transfer_ids.add(b["id"])
                break
    return transfer_ids
