from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import text

from dodoo.addons.account.models.account_sequence import ACCOUNT_SEQUENCE_DDL

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_account_move_state_date ON account_move (state, date)",
    "CREATE INDEX IF NOT EXISTS idx_account_move_line_move_id ON account_move_line (move_id)",
    "CREATE INDEX IF NOT EXISTS idx_account_move_line_display_type ON account_move_line (display_type)",
    "CREATE INDEX IF NOT EXISTS idx_account_account_type ON account_account (account_type)",
    "CREATE INDEX IF NOT EXISTS idx_account_move_line_account_reconciled ON account_move_line (account_id, reconciled)",
]

_PARTNER_FK_COLUMNS = [
    "ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS property_account_receivable_id INTEGER",
    "ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS property_account_payable_id INTEGER",
    "ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS property_payment_term_id INTEGER",
    "ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS property_supplier_payment_term_id INTEGER",
    # 009-customer-database, ADR-046: customer designation + per-customer currency override.
    "ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS customer_rank INTEGER DEFAULT 0",
    "ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS property_currency_id INTEGER",
]

# Fiscal lock dates (FR-031, ADR-039) and realized/unrealized FX gain-loss accounts (FR-025,
# ADR-042) — added to `res_company` (owned by `base`) the same way `_PARTNER_FK_COLUMNS` above
# extends `res_partner`, so `base` keeps no dependency on `account` (research.md D5).
_COMPANY_LOCK_COLUMNS = [
    "ALTER TABLE res_company ADD COLUMN IF NOT EXISTS fiscalyear_lock_date DATE",
    "ALTER TABLE res_company ADD COLUMN IF NOT EXISTS tax_lock_date DATE",
    "ALTER TABLE res_company ADD COLUMN IF NOT EXISTS sale_lock_date DATE",
    "ALTER TABLE res_company ADD COLUMN IF NOT EXISTS purchase_lock_date DATE",
]

_COMPANY_EXCHANGE_COLUMNS = [
    "ALTER TABLE res_company ADD COLUMN IF NOT EXISTS income_currency_exchange_account_id INTEGER",
    "ALTER TABLE res_company ADD COLUMN IF NOT EXISTS expense_currency_exchange_account_id INTEGER",
]

# Fiscal-year-end (FR-037, ADR-044) — defaults to the calendar year, matching Odoo's own default.
_COMPANY_FISCAL_YEAR_COLUMNS = [
    "ALTER TABLE res_company ADD COLUMN IF NOT EXISTS fiscalyear_last_month INTEGER DEFAULT 12",
    "ALTER TABLE res_company ADD COLUMN IF NOT EXISTS fiscalyear_last_day INTEGER DEFAULT 31",
]

# Trigram similarity for reconciliation match-suggestion ranking (FR-021, ADR-042).
_EXTENSIONS = [
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
]

_DEFAULT_COA = [
    ("1000", "Accounts Receivable", "asset_receivable", True),
    ("1010", "Cash", "asset_cash", False),
    ("1020", "Bank", "asset_cash", False),
    ("1100", "Inventory", "asset_current", False),
    ("1200", "Prepaid Expenses", "asset_prepayments", False),
    ("1500", "Fixed Assets", "asset_fixed", False),
    ("2000", "Accounts Payable", "liability_payable", True),
    ("2010", "Credit Card", "liability_credit_card", False),
    ("2100", "Current Liabilities", "liability_current", False),
    ("2500", "VAT Collected", "liability_current", False),
    ("2510", "VAT Deductible", "asset_current", False),
    ("3000", "Share Capital", "equity", False),
    ("3100", "Retained Earnings", "equity_unaffected", False),
    ("4000", "Revenue", "income", False),
    ("4100", "Other Income", "income_other", False),
    ("5000", "Cost of Goods Sold", "expense_direct_cost", False),
    ("5100", "Operating Expenses", "expense", False),
    ("5200", "Other Expenses", "expense_other", False),
    ("5300", "Depreciation", "expense_depreciation", False),
    ("9000", "Off-Balance Sheet", "off_balance", False),
]

# FR-001, ADR-037: group ranges for the default COA's own code prefixes (1000s
# assets ... 9000s off-balance).
_DEFAULT_ACCOUNT_GROUPS = [
    ("Assets", "1000", "1999"),
    ("Liabilities", "2000", "2999"),
    ("Equity", "3000", "3999"),
    ("Income", "4000", "4999"),
    ("Expenses", "5000", "5999"),
    ("Off-Balance Sheet", "9000", "9999"),
]

_DEFAULT_JOURNALS = [
    ("Customer Invoices", "INV", "sale"),
    ("Vendor Bills", "BILL", "purchase"),
    ("Cash", "CSH", "cash"),
    ("Bank", "BNK", "bank"),
    ("Miscellaneous", "MISC", "general"),
]


async def seed_account_data(env: Environment) -> None:
    from dodoo.addons.account.models.account_account import AccountAccount

    async with env.dml_conn() as conn:
        await conn.execute(text(ACCOUNT_SEQUENCE_DDL))

        # Add accounting FK columns to res_partner / res_company
        for ddl in (
            _PARTNER_FK_COLUMNS
            + _COMPANY_LOCK_COLUMNS
            + _COMPANY_EXCHANGE_COLUMNS
            + _COMPANY_FISCAL_YEAR_COLUMNS
        ):
            try:
                await conn.execute(text(ddl))
            except Exception:
                pass

        for ext_sql in _EXTENSIONS:
            try:
                await conn.execute(text(ext_sql))
            except Exception:
                _log.warning("Could not create extension: %s", ext_sql)

        for idx_sql in _INDEXES:
            try:
                await conn.execute(text(idx_sql))
            except Exception:
                pass

        await conn.commit()

    from dodoo.addons.account.data.indexes import PERF_INDEXES, ensure_indexes

    await ensure_indexes(env, PERF_INDEXES)

    _log.info(
        "Created account_sequence table, res_partner/res_company FK columns, "
        "pg_trgm extension, and indexes"
    )

    from dodoo.addons.account.data.groups import seed_groups

    await seed_groups(env)
    _log.info("Seeded Accounting User/Manager groups")

    async with env.dml_conn() as conn:
        result = await conn.execute(text("SELECT id FROM res_company LIMIT 1"))
        row = result.fetchone()
        if not row:
            _log.warning("No company found; skipping account seed data")
            return
        company_id = row[0]

        result = await conn.execute(
            text("SELECT COUNT(*) FROM account_account WHERE company_id = :cid"),
            {"cid": company_id},
        )
        if result.scalar_one() > 0:
            _log.info("Chart of accounts already seeded; skipping")
            return

    await _seed_account_groups(env, company_id)

    for code, name, account_type, reconcile in _DEFAULT_COA:
        await AccountAccount.create(
            env,
            {
                "code": code,
                "name": name,
                "account_type": account_type,
                "reconcile": reconcile,
                "company_id": company_id,
                "active": True,
            },
        )

    _log.info("Seeded default chart of accounts (%d accounts)", len(_DEFAULT_COA))

    await _seed_journals(env, company_id)
    await _seed_taxes(env, company_id)
    await _seed_partners(env, company_id)


async def _seed_account_groups(env: Environment, company_id: int) -> None:
    from dodoo.addons.account.models.account_account import AccountAccountGroup

    async with env.dml_conn() as conn:
        result = await conn.execute(
            text("SELECT COUNT(*) FROM account_account_group WHERE company_id = :cid"),
            {"cid": company_id},
        )
        if result.scalar_one() > 0:
            _log.info("Account groups already seeded; skipping")
            return

    for name, prefix_start, prefix_end in _DEFAULT_ACCOUNT_GROUPS:
        await AccountAccountGroup.create(
            env,
            {
                "name": name,
                "code_prefix_start": prefix_start,
                "code_prefix_end": prefix_end,
                "company_id": company_id,
            },
        )

    _log.info("Seeded default account groups (%d groups)", len(_DEFAULT_ACCOUNT_GROUPS))


async def _seed_journals(env: Environment, company_id: int) -> None:
    from dodoo.addons.account.models.account_journal import AccountJournal

    async with env.dml_conn() as conn:
        result = await conn.execute(
            text("SELECT COUNT(*) FROM account_journal WHERE company_id = :cid"),
            {"cid": company_id},
        )
        if result.scalar_one() > 0:
            _log.info("Journals already seeded; skipping")
            return

    # Fetch account IDs needed for journal defaults
    async with env.dml_conn() as conn:
        rows = await conn.execute(
            text("SELECT code, id FROM account_account WHERE company_id=:cid"),
            {"cid": company_id},
        )
        acct_by_code = {r[0]: r[1] for r in rows}

    for name, code, jtype in _DEFAULT_JOURNALS:
        vals: dict = {"name": name, "code": code, "type": jtype, "company_id": company_id}
        if jtype == "cash":
            acct_id = acct_by_code.get("1010")
            if acct_id:
                vals["default_account_id"] = acct_id
        elif jtype == "bank":
            acct_id = acct_by_code.get("1020")
            if acct_id:
                vals["default_account_id"] = acct_id
        await AccountJournal.create(env, vals)

    _log.info("Seeded default journals")


async def _seed_taxes(env: Environment, company_id: int) -> None:
    from dodoo.addons.account.models.account_tax import (
        AccountTax,
        AccountTaxGroup,
        AccountTaxRepartitionLine,
    )

    async with env.dml_conn() as conn:
        result = await conn.execute(
            text("SELECT COUNT(*) FROM account_tax WHERE company_id = :cid"),
            {"cid": company_id},
        )
        if result.scalar_one() > 0:
            _log.info("Taxes already seeded; skipping")
            return

        # Get VAT Collected and VAT Deductible account IDs
        vat_col = await conn.execute(
            text(
                "SELECT id FROM account_account WHERE code='2500' AND company_id=:cid LIMIT 1"
            ),
            {"cid": company_id},
        )
        vat_col_id = vat_col.scalar_one_or_none()

        vat_ded = await conn.execute(
            text(
                "SELECT id FROM account_account WHERE code='2510' AND company_id=:cid LIMIT 1"
            ),
            {"cid": company_id},
        )
        vat_ded_id = vat_ded.scalar_one_or_none()

    group_id = await AccountTaxGroup.create(
        env, {"name": "VAT", "sequence": 10, "company_id": company_id}
    )

    # Sale VAT 20%
    sale_tax_id = await AccountTax.create(
        env,
        {
            "name": "Tax 20.00%",
            "type_tax_use": "sale",
            "amount_type": "percent",
            "amount": "20",
            "price_include": False,
            "tax_group_id": group_id,
            "company_id": company_id,
            "active": True,
        },
    )
    if vat_col_id:
        await AccountTaxRepartitionLine.create(
            env,
            {
                "tax_id": sale_tax_id,
                "document_type": "invoice",
                "repartition_type": "base",
                "factor_percent": "100",
                "sequence": 1,
            },
        )
        await AccountTaxRepartitionLine.create(
            env,
            {
                "tax_id": sale_tax_id,
                "document_type": "invoice",
                "repartition_type": "tax",
                "factor_percent": "100",
                "account_id": vat_col_id,
                "sequence": 2,
            },
        )

    # Purchase VAT 20%
    purch_tax_id = await AccountTax.create(
        env,
        {
            "name": "Tax 20.00% (Purchase)",
            "type_tax_use": "purchase",
            "amount_type": "percent",
            "amount": "20",
            "price_include": False,
            "tax_group_id": group_id,
            "company_id": company_id,
            "active": True,
        },
    )
    if vat_ded_id:
        await AccountTaxRepartitionLine.create(
            env,
            {
                "tax_id": purch_tax_id,
                "document_type": "invoice",
                "repartition_type": "base",
                "factor_percent": "100",
                "sequence": 1,
            },
        )
        await AccountTaxRepartitionLine.create(
            env,
            {
                "tax_id": purch_tax_id,
                "document_type": "invoice",
                "repartition_type": "tax",
                "factor_percent": "100",
                "account_id": vat_ded_id,
                "sequence": 2,
            },
        )

    _log.info("Seeded default taxes (20%% sale + 20%% purchase VAT)")


async def _seed_partners(env: Environment, company_id: int) -> None:
    from dodoo.addons.base.models.res_partner import ResPartner

    async with env.dml_conn() as conn:
        result = await conn.execute(
            text("SELECT COUNT(*) FROM res_partner WHERE company_id = :cid"),
            {"cid": company_id},
        )
        if result.scalar_one() > 0:
            _log.info("Partners already seeded; skipping")
            return

    await ResPartner.create(
        env,
        {
            "name": "Customer Corp",
            "is_company": True,
            "company_id": company_id,
            "active": True,
        },
    )
    await ResPartner.create(
        env,
        {
            "name": "Vendor Corp",
            "is_company": True,
            "company_id": company_id,
            "active": True,
        },
    )
    _log.info("Seeded default partners")
