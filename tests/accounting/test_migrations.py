"""Schema assertions for 008-accounting-parity (extended per user story). Requires PostgreSQL."""

from __future__ import annotations

from sqlalchemy import text

# (table_name, column_name) pairs expected to exist once the whole feature lands.
EXPECTED_COLUMNS: list[tuple[str, str]] = [
    ("res_currency_rate", "currency_id"),
    ("res_currency_rate", "rate_date"),
    ("res_currency_rate", "rate"),
    ("res_company", "fiscalyear_lock_date"),
    ("res_company", "tax_lock_date"),
    ("res_company", "sale_lock_date"),
    ("res_company", "purchase_lock_date"),
    ("res_company", "income_currency_exchange_account_id"),
    ("res_company", "expense_currency_exchange_account_id"),
    ("res_company", "fiscalyear_last_month"),
    ("res_company", "fiscalyear_last_day"),
    ("account_account_tag", "name"),
    ("account_move_line", "discount"),
    ("account_tax_repartition_line_tag_rel", "repartition_line_id"),
    ("account_payment_term_line", "next_month"),
    ("account_payment_term", "early_payment_discount_account_id"),
    ("account_move", "invoice_cash_rounding_id"),
    ("account_move", "inalterable_hash"),
    ("account_move", "secure_sequence_number"),
    ("account_move", "debit_origin_id"),
    ("account_move", "down_payment_origin_id"),
    ("account_account", "group_id"),
    ("account_journal", "restrict_mode_hash_table"),
    # 009-customer-database (ADR-046)
    ("res_partner", "street"),
    ("res_partner", "city"),
    ("res_partner", "state_id"),
    ("res_partner", "zip"),
    ("res_partner", "country_id"),
    ("res_partner", "customer_rank"),
    ("res_partner", "property_currency_id"),
    # 010-vendor-database (ADR-049)
    ("res_partner", "supplier_rank"),
]

EXPECTED_TABLES: list[str] = [
    "analytic_plan",
    "analytic_account",
    "res_currency_rate",
    "account_account_tag",
    "account_bank_statement",
    "account_bank_statement_line",
    "account_cash_rounding",
    "account_lock_exception",
]


async def test_accounting_manager_group_seeded(env):
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT 1 FROM res_groups WHERE name = 'Accounting Manager'")
        )
    assert row.fetchone()


async def test_expected_tables_present(env):
    async with env.dml_conn() as conn:
        rows = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
        )
        present = {r[0] for r in rows}
    missing = [t for t in EXPECTED_TABLES if t not in present]
    assert not missing, f"missing tables: {missing}"


async def test_expected_columns_present(env):
    async with env.dml_conn() as conn:
        missing = []
        for table, column in EXPECTED_COLUMNS:
            row = await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = :c"
                ),
                {"t": table, "c": column},
            )
            if not row.fetchone():
                missing.append(f"{table}.{column}")
    assert not missing, f"missing columns: {missing}"


async def test_pg_trgm_extension_enabled(env):
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
        )
    assert row.fetchone()
