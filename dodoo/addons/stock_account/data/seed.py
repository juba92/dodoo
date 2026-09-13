"""``seed_stock_account_data`` — the Inventory Accounting addon's ``post_install`` entry point.

Order: schema extension (costing/valuation columns) → ``ir_model`` row → indexes → default
accounts/journal + category defaults. Idempotent.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from dodoo.addons.product.data.ir_model_sync import sync_ir_model
from dodoo.addons.stock_account.data.indexes import INDEXES, ensure_indexes
from dodoo.addons.stock_account.validators import and_domain
from dodoo.addons.stock_account.data.product_category_ext import add_valuation_columns
from dodoo.addons.stock_account.data.product_product_ext import add_stock_avg_cost_column

_log = logging.getLogger(__name__)

IR_MODELS: list[tuple[str, str]] = [("stock.valuation.layer", "stock_valuation_layer")]


async def _seed_accounts_and_journal(env: Any) -> None:
    from dodoo.addons.account.models.account_account import AccountAccount
    from dodoo.addons.account.models.account_journal import AccountJournal

    async with env.dml_conn() as conn:
        companies = (await conn.execute(text("SELECT id FROM res_company"))).fetchall()

    for (company_id,) in companies:
        async with env.dml_conn() as conn:
            existing = await conn.execute(
                text(
                    "SELECT id FROM account_journal WHERE company_id = :c AND name = 'Inventory Valuation'"
                ),
                {"c": company_id},
            )
            if existing.fetchone():
                continue

        valuation_ids = await AccountAccount.search(
            env, and_domain(["company_id", "=", company_id], ["code", "=", "1100"])
        )
        valuation_acct = valuation_ids[0] if valuation_ids else None

        input_acct = await AccountAccount.create(
            env,
            {
                "code": "1101",
                "name": "Stock Interim (Received)",
                "account_type": "asset_current",
                "company_id": company_id,
            },
        )
        output_acct = await AccountAccount.create(
            env,
            {
                "code": "1102",
                "name": "Stock Interim (Delivered)",
                "account_type": "liability_current",
                "company_id": company_id,
            },
        )
        await AccountJournal.create(
            env,
            {
                "name": "Inventory Valuation",
                "code": "STJ",
                "type": "general",
                "company_id": company_id,
            },
        )

        if valuation_acct:
            async with env.dml_conn() as conn:
                await conn.execute(
                    text(
                        "UPDATE product_category SET "
                        "property_stock_valuation_account_id = :v, "
                        "property_stock_input_account_id = :i, "
                        "property_stock_output_account_id = :o "
                        "WHERE property_stock_valuation_account_id IS NULL"
                    ),
                    {"v": valuation_acct, "i": input_acct, "o": output_acct},
                )
                await conn.commit()


async def seed_stock_account_data(env: Any) -> None:
    await add_valuation_columns(env)
    await add_stock_avg_cost_column(env)
    await sync_ir_model(env, IR_MODELS)
    await ensure_indexes(env, INDEXES)
    await _seed_accounts_and_journal(env)
    _log.info("stock_account: seed complete")
