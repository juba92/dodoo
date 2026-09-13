"""REST action routes for costing configuration and the valuation report (US8, FR-077…079)."""

from __future__ import annotations

from sqlalchemy import text

from fastapi import Request

from dodoo.addons.stock.security import GROUP_MANAGER
from dodoo.addons.stock_account.http import json_err, json_ok
from dodoo.addons.stock_account.validators import (
    CategoryValuationConfig,
    require_groups,
    validate,
)
from dodoo.core.context import get_uid
from dodoo.core.exceptions import AccessError, DodooError
from dodoo.http.routing import route


@route("/stock_account/category/{category_id}/configure", methods=["GET"], auth="session")
async def get_category_configure(request: Request, category_id: int):
    env = request.app.state.env
    try:
        await require_groups(env, get_uid(), GROUP_MANAGER)
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT costing_method, property_stock_valuation_account_id, "
                    "property_stock_input_account_id, property_stock_output_account_id "
                    "FROM product_category WHERE id = :id"
                ),
                {"id": category_id},
            )
            r = row.fetchone()
        if not r:
            return json_err("category_not_found", status_code=404)
        return json_ok(
            {
                "category_id": category_id,
                "costing_method": r[0],
                "property_stock_valuation_account_id": r[1],
                "property_stock_input_account_id": r[2],
                "property_stock_output_account_id": r[3],
            }
        )
    except AccessError as exc:
        return json_err(str(exc), status_code=403)


@route("/stock_account/category/{category_id}/configure", methods=["POST"], auth="session")
async def set_category_configure(request: Request, category_id: int):
    env = request.app.state.env
    try:
        await require_groups(env, get_uid(), GROUP_MANAGER)
        payload = validate(CategoryValuationConfig, await request.json())
        async with env.dml_conn() as conn:
            await conn.execute(
                text(
                    "UPDATE product_category SET costing_method = :cm, "
                    "property_stock_valuation_account_id = :v, "
                    "property_stock_input_account_id = :i, "
                    "property_stock_output_account_id = :o WHERE id = :id"
                ),
                {
                    "cm": payload.costing_method,
                    "v": payload.property_stock_valuation_account_id,
                    "i": payload.property_stock_input_account_id,
                    "o": payload.property_stock_output_account_id,
                    "id": category_id,
                },
            )
            await conn.commit()
        return json_ok(
            {
                "category_id": category_id,
                "costing_method": payload.costing_method,
                "property_stock_valuation_account_id": payload.property_stock_valuation_account_id,
                "property_stock_input_account_id": payload.property_stock_input_account_id,
                "property_stock_output_account_id": payload.property_stock_output_account_id,
            }
        )
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/stock/valuation/report", methods=["GET"], auth="session")
async def valuation_report(request: Request):
    env = request.app.state.env
    try:
        await require_groups(env, get_uid(), GROUP_MANAGER)
        company_id = request.query_params.get("company_id")
        category_id = request.query_params.get("category_id")
        product_id = request.query_params.get("product_id")

        clauses = ["1 = 1"]
        params: dict = {}
        if company_id:
            clauses.append("svl.company_id = :company_id")
            params["company_id"] = int(company_id)
        if product_id:
            clauses.append("svl.product_id = :product_id")
            params["product_id"] = int(product_id)
        if category_id:
            clauses.append("pt.category_id = :category_id")
            params["category_id"] = int(category_id)

        where = " AND ".join(clauses) if clauses else "1=1"
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT svl.product_id, pt.category_id, "
                    "COALESCE(SUM(CASE WHEN pcat.costing_method = 'fifo' THEN svl.remaining_qty ELSE svl.quantity END), 0) AS qty, "
                    "COALESCE(SUM(CASE WHEN pcat.costing_method = 'fifo' THEN svl.remaining_value ELSE svl.value END), 0) AS value "
                    "FROM stock_valuation_layer svl "
                    "JOIN product_product pp ON pp.id = svl.product_id "
                    "JOIN product_template pt ON pt.id = pp.template_id "
                    "LEFT JOIN product_category pcat ON pcat.id = pt.category_id "
                    f"WHERE {where} "
                    "GROUP BY svl.product_id, pt.category_id"
                ),
                params,
            )
            data = [dict(r._mapping) for r in rows]
        total_value = sum(r["value"] for r in data)
        return json_ok(
            {
                "rows": [
                    {
                        "product_id": r["product_id"],
                        "category_id": r["category_id"],
                        "quantity_on_hand": r["qty"],
                        "value": r["value"],
                    }
                    for r in data
                ],
                "total_value": total_value,
            }
        )
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/stock/valuation/reconcile", methods=["GET"], auth="session")
async def valuation_reconcile(request: Request):
    env = request.app.state.env
    try:
        await require_groups(env, get_uid(), GROUP_MANAGER)
        category_id = int(request.query_params["category_id"])

        async with env.dml_conn() as conn:
            cat_row = await conn.execute(
                text(
                    "SELECT property_stock_valuation_account_id FROM product_category WHERE id = :c"
                ),
                {"c": category_id},
            )
            r = cat_row.fetchone()
        if not r or not r[0]:
            return json_err("category_not_configured", status_code=404)
        account_id = r[0]

        from dodoo.addons.account.models.account_account import AccountAccount

        balance = await AccountAccount.get_balance(env, account_id)
        ledger_net = float(balance["net"])

        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT COALESCE(SUM(CASE WHEN pcat.costing_method = 'fifo' THEN svl.remaining_value ELSE svl.value END), 0) "
                    "FROM stock_valuation_layer svl "
                    "JOIN product_product pp ON pp.id = svl.product_id "
                    "JOIN product_template pt ON pt.id = pp.template_id "
                    "JOIN product_category pcat ON pcat.id = pt.category_id "
                    "WHERE pt.category_id = :c"
                ),
                {"c": category_id},
            )
            report_value = float(row.scalar_one())

        return json_ok(
            {
                "category_id": category_id,
                "report_value": report_value,
                "ledger_net": ledger_net,
                "matches": abs(report_value - ledger_net) < 0.01,
            }
        )
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))
