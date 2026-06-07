# JSON-RPC Contracts: Accounting Module

**Protocol**: JSON-RPC 2.0 via existing `execute_kw` endpoint at `POST /web/dataset/call_kw`

All requests require `X-Session-Token` header. All responses follow the existing dodoo JSON-RPC envelope.

---

## Standard CRUD Methods (all models)

These work on every accounting model via the existing `execute_kw` dispatcher:

```json
{
  "jsonrpc": "2.0",
  "method": "call",
  "params": {
    "model": "<model_name>",
    "method": "<method>",
    "args": [<positional args>],
    "kwargs": {<keyword args>}
  }
}
```

| method | args | kwargs | Returns |
|--------|------|--------|---------|
| `fields_get` | `[]` | `{"attributes": ["type","string","required"]}` | `{field_name: {type, string, required}}` |
| `search_read` | `[[domain]]` | `{"fields": [...], "limit": N, "offset": N, "order": "field asc"}` | `[{id, ...fields}]` |
| `read` | `[[ids]]` | `{"fields": [...]}` | `[{id, ...fields}]` |
| `create` | `[{vals}]` | `{}` | `id (int)` |
| `write` | `[[ids], {vals}]` | `{}` | `true` |
| `unlink` | `[[ids]]` | `{}` | `true` |

---

## Custom Action Methods

### account.move — action_post

Posts a draft journal entry. Assigns sequence name and locks the entry.

**Request**:
```json
{
  "model": "account.move",
  "method": "action_post",
  "args": [[<move_id>]],
  "kwargs": {}
}
```

**Success response**: `{"result": true}`

**Error response** (imbalanced):
```json
{
  "error": {
    "code": 400,
    "message": "Journal entry is not balanced. Debit: 1200.00, Credit: 1000.00. Difference: 200.00"
  }
}
```

**Error response** (already posted):
```json
{"error": {"code": 400, "message": "Move INV/2026/0001 is already posted."}}
```

---

### account.move — action_reset_to_draft

Resets a posted entry back to draft. Blocked if any reconciliation exists.

**Request**:
```json
{
  "model": "account.move",
  "method": "action_reset_to_draft",
  "args": [[<move_id>]],
  "kwargs": {}
}
```

**Success**: `{"result": true}`

**Error** (reconciled):
```json
{"error": {"code": 400, "message": "Cannot reset to draft: move has reconciled lines. Unreconcile first."}}
```

---

### account.move — action_reverse

Creates a reversal (credit note / counter-entry) for a posted move.

**Request**:
```json
{
  "model": "account.move",
  "method": "action_reverse",
  "args": [[<move_id>]],
  "kwargs": {
    "date": "2026-06-15",
    "reason": "Correction"
  }
}
```

**Success**: `{"result": <new_reversal_move_id>}`

---

### account.move — compute_tax_lines

Recomputes tax and payment-term lines from current product lines. Called automatically on create/write of product lines; also callable explicitly.

**Request**:
```json
{
  "model": "account.move",
  "method": "compute_tax_lines",
  "args": [[<move_id>]],
  "kwargs": {}
}
```

**Success**: `{"result": true}`

---

### account.payment — action_post

Posts a payment, creating the associated journal entry.

**Request**:
```json
{
  "model": "account.payment",
  "method": "action_post",
  "args": [[<payment_id>]],
  "kwargs": {}
}
```

**Success**: `{"result": true}`

---

### account.payment — register_against_invoices

Registers a payment against one or more invoice moves and auto-reconciles the AR/AP lines.

**Request**:
```json
{
  "model": "account.payment",
  "method": "register_against_invoices",
  "args": [[<payment_id>]],
  "kwargs": {
    "invoice_ids": [42, 43]
  }
}
```

**Success**: `{"result": {"reconciled_invoice_ids": [42, 43], "fully_paid": [42]}}`

---

### account.partial.reconcile — reconcile_lines

Creates a partial reconcile record between a debit and credit line.

**Request**:
```json
{
  "model": "account.partial.reconcile",
  "method": "reconcile_lines",
  "args": [[]],
  "kwargs": {
    "debit_line_id": 101,
    "credit_line_id": 202,
    "amount": 500.00
  }
}
```

**Success**: `{"result": <partial_reconcile_id>}`

**Error** (amount exceeds residual):
```json
{"error": {"code": 400, "message": "Reconcile amount 500.00 exceeds minimum residual 300.00."}}
```

---

### account.partial.reconcile — unreconcile

Removes a partial reconcile record and restores residuals.

**Request**:
```json
{
  "model": "account.partial.reconcile",
  "method": "unreconcile",
  "args": [[<partial_reconcile_id>]],
  "kwargs": {}
}
```

**Success**: `{"result": true}`

---

## Report Methods

All report models are read-only. They do not support create/write/unlink.

### account.report.trial_balance — get_report

**Request**:
```json
{
  "model": "account.report.trial_balance",
  "method": "get_report",
  "args": [[]],
  "kwargs": {
    "date_from": "2026-01-01",
    "date_to": "2026-06-30"
  }
}
```

**Response**:
```json
{
  "result": [
    {
      "code": "1000",
      "name": "Accounts Receivable",
      "account_type": "asset_receivable",
      "total_debit": 5000.00,
      "total_credit": 3000.00,
      "net_balance": 2000.00
    }
  ],
  "totals": {
    "total_debit": 50000.00,
    "total_credit": 50000.00,
    "balanced": true
  }
}
```

---

### account.report.general_ledger — get_report

**Request**:
```json
{
  "model": "account.report.general_ledger",
  "method": "get_report",
  "args": [[]],
  "kwargs": {
    "account_id": 5,
    "date_from": "2026-01-01",
    "date_to": "2026-06-30"
  }
}
```

**Response**:
```json
{
  "result": [
    {
      "date": "2026-01-15",
      "move_name": "INV/2026/0001",
      "partner_name": "Acme Corp",
      "label": "Invoice product line",
      "debit": 1200.00,
      "credit": 0.00,
      "running_balance": 1200.00
    }
  ]
}
```

---

### account.report.profit_loss — get_report

**Request**:
```json
{
  "model": "account.report.profit_loss",
  "method": "get_report",
  "args": [[]],
  "kwargs": {"date_from": "2026-01-01", "date_to": "2026-06-30"}
}
```

**Response**:
```json
{
  "result": {
    "income": [{"code": "4000", "name": "Revenue", "balance": 20000.00}],
    "expense": [{"code": "5000", "name": "COGS", "balance": 12000.00}],
    "net_profit": 8000.00
  }
}
```

---

### account.report.balance_sheet — get_report

**Request**:
```json
{
  "model": "account.report.balance_sheet",
  "method": "get_report",
  "args": [[]],
  "kwargs": {"date": "2026-06-30"}
}
```

**Response**:
```json
{
  "result": {
    "assets": [{"code": "1000", "name": "Accounts Receivable", "balance": 2000.00}],
    "liabilities": [{"code": "2000", "name": "Accounts Payable", "balance": 500.00}],
    "equity": [{"code": "3000", "name": "Share Capital", "balance": 1500.00}],
    "totals": {"assets": 2000.00, "liabilities_and_equity": 2000.00, "balanced": true}
  }
}
```

---

### account.report.aged_receivable / aged_payable — get_report

**Request**:
```json
{
  "model": "account.report.aged_receivable",
  "method": "get_report",
  "args": [[]],
  "kwargs": {"date": "2026-06-30"}
}
```

**Response**:
```json
{
  "result": [
    {
      "partner_name": "Acme Corp",
      "total": 1200.00,
      "bucket_0_30": 1200.00,
      "bucket_31_60": 0.00,
      "bucket_61_90": 0.00,
      "bucket_over_90": 0.00
    }
  ]
}
```

---

## Error Response Format

All errors follow the existing dodoo JSON-RPC error envelope:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": <http_status>,
    "message": "<human-readable message>",
    "data": {
      "type": "ValidationError|AccessError|NotFoundError",
      "detail": "<optional extra detail>"
    }
  }
}
```

| HTTP Status | Meaning |
|-------------|---------|
| 400 | Validation error (imbalanced move, invalid state transition, constraint violation) |
| 401 | No valid session token |
| 403 | Access denied (write to posted move, cross-company reconcile) |
| 404 | Record not found |
| 500 | Unexpected server error |
