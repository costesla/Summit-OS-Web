---
name: client-identity-resolution
description: >-
  Best practices and runbooks for resolving and deduplicating customer identities across messy real-world variants
  (Apple Private Relay emails, name spelling variations, nickname aliases) without corrupting historical financial ledgers.
---

# Client Identity Resolution & Ledger Integrity

This skill defines the rules for mapping chaotic real-world passenger contact variations into clean canonical entities.

---

## 1. Core Principles

1. **Non-Destructive Resolution:** Never run destructive SQL `UPDATE` queries on raw historical invoices or platform ride records. Raw logs must preserve the exact string captured at transaction time.
2. **Canonical Mapping Layer:** Use a dedicated canonical mapping table or view join (`Clients.Canonical` or `vw_CanonicalClients`) that maps:
   * Apple Private Relay tokens (`*@privaterelay.appleid.com`) $\rightarrow$ Master Client ID.
   * Spelling & Nickname Aliases (`Jacquelyn` / `Jackie`, `Esmeralda` / `Esme`) $\rightarrow$ Master Client ID.
3. **Inactive & Denylist Handling:**
   * Centralize inactive/written-off client predicates in a single source of truth (`inactive_invoice_predicate`).
   * Never hardcode client name filters inside scattered UI components.
