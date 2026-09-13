"""``stock.valuation.layer`` — costing-method valuation engine (ADR-033).

Triggered exclusively by ``stock_account/__init__.py``'s import-time wrap of
``StockMove.action_set_state`` (ADR-034/D6) — never called from ``stock``'s own code.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.addons.stock_account.validators import and_domain
from dodoo.core.fields import Float, Many2one, Monetary
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)


class StockValuationLayer(BaseModel):
    _name = "stock.valuation.layer"

    product_id = Many2one("product.product", required=True)
    stock_move_id = Many2one("stock.move", required=True)
    quantity = Float(required=True)
    unit_cost = Monetary()
    value = Monetary()
    remaining_qty = Float(default=0)
    remaining_value = Monetary()
    account_move_id = Many2one("account.move")
    company_id = Many2one("res.company")

    @classmethod
    async def value_move(cls, env: Environment, move_id: int, uid: int | None = None) -> int | None:
        """Value a validated ``stock.move`` and post a balanced journal entry (FR-072…075).
        Returns the created layer id, or ``None`` when the move isn't valuation-relevant
        (untracked product, or a pure internal-to-internal transfer)."""
        from dodoo.addons.stock.models.stock_location import StockLocation
        from dodoo.addons.stock.models.stock_move import StockMove

        move = (
            await StockMove.read(
                env, [move_id], ["product_id", "location_src_id", "location_dest_id"]
            )
        )[0]

        async with env.dml_conn() as conn:
            row = await conn.execute(
                text("SELECT COALESCE(SUM(qty_done), 0) FROM stock_move_line WHERE move_id = :m"),
                {"m": move_id},
            )
            qty_done = float(row.scalar_one())
        if qty_done <= 0:
            return None

        from dodoo.addons.product.models.product_product import ProductProduct
        from dodoo.addons.product.models.product_template import ProductTemplate

        product = (await ProductProduct.read(env, [move["product_id"]], ["template_id"]))[0]
        template = (
            await ProductTemplate.read(
                env,
                [product["template_id"]],
                ["is_storable", "category_id", "standard_price", "company_id"],
            )
        )[0]
        if not template["is_storable"]:
            return None

        locs = await StockLocation.read(
            env,
            [move["location_src_id"], move["location_dest_id"]],
            ["id", "usage", "warehouse_id", "company_id"],
        )
        by_id = {r["id"]: r for r in locs}
        src_loc = by_id[move["location_src_id"]]
        dst_loc = by_id[move["location_dest_id"]]

        incoming = dst_loc["usage"] == "internal" and src_loc["usage"] != "internal"
        outgoing = src_loc["usage"] == "internal" and dst_loc["usage"] != "internal"
        if not incoming and not outgoing:
            return None

        category_id = template["category_id"]
        if not category_id:
            return None
        async with env.dml_conn() as conn:
            cat_row = await conn.execute(
                text(
                    "SELECT costing_method, property_stock_valuation_account_id, "
                    "property_stock_input_account_id, property_stock_output_account_id "
                    "FROM product_category WHERE id = :c"
                ),
                {"c": category_id},
            )
            cat = cat_row.fetchone()
        if not cat or not all(cat[1:]):
            return None
        costing_method, val_acct, in_acct, out_acct = cat

        company_id = (dst_loc["company_id"] if incoming else src_loc["company_id"]) or template.get(
            "company_id"
        )
        if not company_id:
            async with env.dml_conn() as conn:
                row = await conn.execute(text("SELECT id FROM res_company LIMIT 1"))
                company_id = row.scalar_one()

        if incoming:
            layer_id, debit_acct, credit_acct = await cls._value_incoming(
                env, move, move_id, product, qty_done, costing_method, company_id, val_acct, in_acct
            )
        else:
            layer_id, debit_acct, credit_acct = await cls._value_outgoing(
                env, move, move_id, product, qty_done, costing_method, company_id, val_acct, out_acct
            )
        if layer_id is None:
            return None

        layer = (await super().read(env, [layer_id], ["value"]))[0]
        account_move_id = await cls._post_journal_entry(
            env, company_id, debit_acct, credit_acct, abs(layer["value"]), uid=uid
        )
        await super().write(env, [layer_id], {"account_move_id": account_move_id})
        return layer_id

    # ------------------------------------------------------------------ costing methods

    @classmethod
    async def _value_incoming(
        cls, env, move, move_id, product, qty_done, costing_method, company_id, val_acct, in_acct
    ):
        from dodoo.addons.product.models.product_template import ProductTemplate

        template = (
            await ProductTemplate.read(env, [product["template_id"]], ["standard_price"])
        )[0]
        unit_cost = float(template["standard_price"] or 0)
        value = qty_done * unit_cost

        remaining_qty = qty_done if costing_method == "fifo" else 0
        remaining_value = value if costing_method == "fifo" else 0
        layer_id = await super(StockValuationLayer, cls).create(
            env,
            {
                "product_id": move["product_id"],
                "stock_move_id": move_id,
                "quantity": qty_done,
                "unit_cost": unit_cost,
                "value": value,
                "remaining_qty": remaining_qty,
                "remaining_value": remaining_value,
                "company_id": company_id,
            },
        )

        if costing_method == "average":
            await cls._recompute_average(env, move["product_id"], qty_done, unit_cost)

        return layer_id, val_acct, in_acct

    @classmethod
    async def _value_outgoing(
        cls, env, move, move_id, product, qty_done, costing_method, company_id, val_acct, out_acct
    ):
        from dodoo.addons.product.models.product_template import ProductTemplate

        if costing_method == "fifo":
            value = await cls._consume_fifo(env, move["product_id"], qty_done)
            unit_cost = value / qty_done if qty_done else 0
        else:
            if costing_method == "average":
                unit_cost = await cls._get_avg_cost(env, move["product_id"])
            else:
                template = (
                    await ProductTemplate.read(env, [product["template_id"]], ["standard_price"])
                )[0]
                unit_cost = float(template["standard_price"] or 0)
            value = qty_done * unit_cost

        layer_id = await super(StockValuationLayer, cls).create(
            env,
            {
                "product_id": move["product_id"],
                "stock_move_id": move_id,
                "quantity": -qty_done,
                "unit_cost": unit_cost,
                "value": -value,
                "company_id": company_id,
            },
        )
        return layer_id, out_acct, val_acct

    @classmethod
    async def _consume_fifo(cls, env: Environment, product_id: int, qty: float) -> float:
        remaining = qty
        total_value = 0.0
        layer_ids = await cls.search(
            env,
            and_domain(["product_id", "=", product_id], ["remaining_qty", ">", 0]),
            order="create_date asc",
        )
        layers = (
            await cls.read(env, layer_ids, ["remaining_qty", "remaining_value"]) if layer_ids else []
        )
        for layer in layers:
            if remaining <= 0:
                break
            take = min(layer["remaining_qty"], remaining)
            layer_unit_cost = (
                layer["remaining_value"] / layer["remaining_qty"] if layer["remaining_qty"] else 0
            )
            take_value = take * layer_unit_cost
            await super(StockValuationLayer, cls).write(
                env,
                [layer["id"]],
                {
                    "remaining_qty": layer["remaining_qty"] - take,
                    "remaining_value": layer["remaining_value"] - take_value,
                },
            )
            total_value += take_value
            remaining -= take
        return total_value

    @classmethod
    async def _get_avg_cost(cls, env: Environment, product_id: int) -> float:
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text("SELECT stock_avg_cost FROM product_product WHERE id = :p"), {"p": product_id}
            )
            r = row.fetchone()
            return float(r[0]) if r else 0.0

    @classmethod
    async def _recompute_average(
        cls, env: Environment, product_id: int, incoming_qty: float, incoming_unit_cost: float
    ) -> None:
        from dodoo.addons.stock.models.stock_quant import StockQuant

        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT COALESCE(SUM(quantity), 0) FROM stock_quant JOIN stock_location "
                    "ON stock_location.id = stock_quant.location_id "
                    "WHERE product_id = :p AND stock_location.usage = 'internal'"
                ),
                {"p": product_id},
            )
            on_hand_after = float(row.scalar_one())
        on_hand_before = on_hand_after - incoming_qty
        old_avg = await cls._get_avg_cost(env, product_id)
        total_qty = on_hand_before + incoming_qty
        new_avg = (
            ((on_hand_before * old_avg) + (incoming_qty * incoming_unit_cost)) / total_qty
            if total_qty > 0
            else incoming_unit_cost
        )
        async with env.dml_conn() as conn:
            await conn.execute(
                text("UPDATE product_product SET stock_avg_cost = :a WHERE id = :p"),
                {"a": new_avg, "p": product_id},
            )
            await conn.commit()

    # ------------------------------------------------------------------ journal posting

    @classmethod
    async def _post_journal_entry(
        cls, env: Environment, company_id: int, debit_acct: int, credit_acct: int, amount: float, uid: int | None = None
    ) -> int:
        from dodoo.addons.account.models.account_move import AccountMove
        from dodoo.addons.account.models.account_move_line import AccountMoveLine

        async with env.dml_conn() as conn:
            row = await conn.execute(
                text("SELECT currency_id FROM res_company WHERE id = :c"), {"c": company_id}
            )
            currency_id = row.scalar_one()
            journal_row = await conn.execute(
                text(
                    "SELECT id FROM account_journal WHERE company_id = :c "
                    "AND name = 'Inventory Valuation' LIMIT 1"
                ),
                {"c": company_id},
            )
            jr = journal_row.fetchone()
        if not jr:
            _log.warning("stock_account: no Inventory Valuation journal for company %s", company_id)
            return None
        journal_id = jr[0]

        today = datetime.date.today()
        move_id = await AccountMove.create(
            env,
            {
                "move_type": "entry",
                "journal_id": journal_id,
                "company_id": company_id,
                "currency_id": currency_id,
                "date": today,
                "state": "draft",
            },
        )
        await AccountMoveLine.create(
            env,
            {
                "move_id": move_id,
                "account_id": debit_acct,
                "date": today,
                "display_type": "product",
                "name": "Inventory valuation",
                "debit": amount,
                "credit": 0,
                "balance": amount,
            },
        )
        await AccountMoveLine.create(
            env,
            {
                "move_id": move_id,
                "account_id": credit_acct,
                "date": today,
                "display_type": "product",
                "name": "Inventory valuation",
                "debit": 0,
                "credit": amount,
                "balance": -amount,
            },
        )
        await AccountMove.action_post(env, [move_id])
        return move_id
