# Quickstart Validation Guide: Accounting Module

**Branch**: `003-accounting` | **Date**: 2026-06-07

This guide proves the accounting module works end-to-end via the existing JSON-RPC interface. All scenarios use `curl` against a running dodoo instance.

---

## Prerequisites

1. dodoo server running: `set -a && source .env && set +a && .venv/bin/python -m dodoo server --port 8069`
2. Authenticate and capture session token:
```bash
TOKEN=$(curl -s -X POST http://localhost:8069/web/session/authenticate \
  -H "Content-Type: application/json" \
  -d '{"login":"admin","password":"admin"}' | jq -r .session_token)
echo "Token: $TOKEN"
```
3. Helper function for JSON-RPC calls:
```bash
rpc() {
  curl -s -X POST http://localhost:8069/web/dataset/call_kw \
    -H "Content-Type: application/json" \
    -H "X-Session-Token: $TOKEN" \
    -d "$1" | jq .
}
```

---

## Scenario 1: Full Customer Invoice Cycle (US1)

Proves: double-entry engine, tax computation, posting, reconciliation, payment_state tracking.

### 1.1 Create a customer invoice
```bash
MOVE_ID=$(rpc '{
  "model": "account.move",
  "method": "create",
  "args": [{"move_type": "out_invoice", "partner_id": 1, "journal_id": 1, "date": "2026-06-07",
            "line_ids": [{"account_id": 4, "name": "Consulting", "debit": 1000, "credit": 0,
                          "tax_ids": [1], "display_type": "product"}]}],
  "kwargs": {}
}' | jq .result)
echo "Move ID: $MOVE_ID"
```

**Expected**: numeric move ID returned; move.state = 'draft'; move.payment_state = 'not_paid'

### 1.2 Verify auto-generated tax and AR lines
```bash
rpc "{\"model\": \"account.move.line\", \"method\": \"search_read\",
     \"args\": [[[\"move_id\", \"=\", $MOVE_ID]]],
     \"kwargs\": {\"fields\": [\"display_type\",\"account_id\",\"debit\",\"credit\"]}}"
```

**Expected**: 3 lines — product (Dr 1000 Revenue), tax (Cr 200 VAT), payment_term (Dr 1200 AR)

### 1.3 Post the invoice
```bash
rpc "{\"model\": \"account.move\", \"method\": \"action_post\", \"args\": [[$MOVE_ID]], \"kwargs\": {}}"
```

**Expected**: `{"result": true}`; move.name = 'INV/2026/0001'; move.state = 'posted'

### 1.4 Verify payment_state = not_paid
```bash
rpc "{\"model\": \"account.move\", \"method\": \"read\", \"args\": [[$MOVE_ID]],
     \"kwargs\": {\"fields\": [\"state\",\"payment_state\",\"name\",\"amount_total\"]}}"
```

**Expected**: `state: posted`, `payment_state: not_paid`, `amount_total: 1200.00`

### 1.5 Register payment
```bash
PAY_ID=$(rpc "{\"model\": \"account.payment\", \"method\": \"create\",
  \"args\": [{\"payment_type\": \"inbound\", \"partner_type\": \"customer\",
              \"partner_id\": 1, \"journal_id\": 3, \"amount\": 1200.00,
              \"date\": \"2026-06-07\"}], \"kwargs\": {}}" | jq .result)
rpc "{\"model\": \"account.payment\", \"method\": \"action_post\", \"args\": [[$PAY_ID]], \"kwargs\": {}}"
rpc "{\"model\": \"account.payment\", \"method\": \"register_against_invoices\",
     \"args\": [[$PAY_ID]], \"kwargs\": {\"invoice_ids\": [$MOVE_ID]}}"
```

**Expected**: invoice payment_state = 'paid'; AR line reconciled = true

---

## Scenario 2: Balance Constraint Rejection (SC-002)

Proves: posting fails for unbalanced entries.

```bash
BAD_MOVE=$(rpc '{
  "model": "account.move",
  "method": "create",
  "args": [{"move_type": "entry", "journal_id": 5, "date": "2026-06-07",
            "line_ids": [{"account_id": 4, "name": "Test", "debit": 500, "credit": 0, "display_type": "product"}]}],
  "kwargs": {}
}' | jq .result)

rpc "{\"model\": \"account.move\", \"method\": \"action_post\", \"args\": [[$BAD_MOVE]], \"kwargs\": {}}"
```

**Expected**: error response with message containing "not balanced" and the imbalance amount (500.00).

---

## Scenario 3: Trial Balance Report (SC-003, SC-004)

Proves: Trial Balance computes in < 5s; totals balance.

```bash
rpc '{"model": "account.report.trial_balance", "method": "get_report",
      "args": [[]], "kwargs": {"date_from": "2026-01-01", "date_to": "2026-12-31"}}'
```

**Expected**: `totals.balanced = true`; `totals.total_debit == totals.total_credit`. Response time < 5 seconds.

---

## Scenario 4: Immutability of Posted Moves (SC-005)

Proves: posted moves cannot be directly modified.

```bash
rpc "{\"model\": \"account.move\", \"method\": \"write\",
     \"args\": [[$MOVE_ID], {\"narration\": \"attempt to edit\"}], \"kwargs\": {}}"
```

**Expected**: error 400 with message about immutability of posted moves.

---

## Scenario 5: Credit Note Reversal (US3)

```bash
REFUND_ID=$(rpc "{\"model\": \"account.move\", \"method\": \"action_reverse\",
  \"args\": [[$MOVE_ID]], \"kwargs\": {\"date\": \"2026-06-10\", \"reason\": \"Test refund\"}}" | jq .result)

rpc "{\"model\": \"account.move\", \"method\": \"action_post\", \"args\": [[$REFUND_ID]], \"kwargs\": {}}"
```

**Expected**: REFUND_ID is a new move with move_type='out_refund'; original invoice payment_state = 'reversed'.

---

## Scenario 6: Chart of Accounts (US5)

Verify seed data installed correctly.

```bash
rpc '{"model": "account.account", "method": "search_read",
      "args": [[]], "kwargs": {"fields": ["code","name","account_type"], "order": "code asc"}}'
```

**Expected**: ≥ 22 accounts; all 18 account types represented; accounts include 1000, 2000, 3000, 4000, 5000.

---

## Scenario 7: Vendor Bill Cycle (US2)

```bash
# Create vendor bill
BILL_ID=$(rpc '{"model": "account.move", "method": "create",
  "args": [{"move_type": "in_invoice", "partner_id": 2, "journal_id": 2,
            "date": "2026-06-07", "invoice_date": "2026-06-01",
            "line_ids": [{"account_id": 5, "name": "Office supplies", "debit": 0, "credit": 500,
                          "tax_ids": [2], "display_type": "product"}]}], "kwargs": {}}' | jq .result)

# Post
rpc "{\"model\": \"account.move\", \"method\": \"action_post\", \"args\": [[$BILL_ID]], \"kwargs\": {}}"
```

**Expected**: bill.name = 'BILL/2026/0001'; bill.state = 'posted'; AP line generated.

---

## Scenario 8: Aged Receivables Report (US8)

```bash
rpc '{"model": "account.report.aged_receivable", "method": "get_report",
      "args": [[]], "kwargs": {"date": "2026-06-30"}}'
```

**Expected**: returns a list with buckets (0-30, 31-60, 61-90, 90+) summing to total outstanding AR.

---

## Pass/Fail Checklist

| Scenario | Expected result | Pass? |
|----------|----------------|-------|
| 1.1 Create invoice | Move ID returned, state=draft | |
| 1.2 Auto tax lines | 3 lines: product + tax + AR | |
| 1.3 Post invoice | name=INV/2026/0001, state=posted | |
| 1.4 Payment state | not_paid before payment | |
| 1.5 Payment + reconcile | paid, AR reconciled | |
| 2 Imbalance rejection | 400 error with imbalance amount | |
| 3 Trial Balance | balanced=true, <5s | |
| 4 Immutability | 400 error on write to posted | |
| 5 Credit note | out_refund created, original=reversed | |
| 6 Chart of accounts | ≥22 accounts, all types covered | |
| 7 Vendor bill | BILL/2026/0001, state=posted | |
| 8 Aged receivables | Bucketed AR report returned | |
