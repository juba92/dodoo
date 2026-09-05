"""Country-driven localization service.

Applying a package idempotently seeds a currency, sales/purchase taxes (mapped to the
company's tax accounts), and Domestic/Export fiscal positions into the existing ``account``
models, then switches the active company defaults. It never issues UPDATE/DELETE against
posted accounting data, and a functional-currency change is blocked behind an explicit
confirmation when posted entries exist (FR-026..FR-031).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.addons.localization.packs import get_pack

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)


async def _scalar(conn, sql: str, params: dict | None = None):
    row = await conn.execute(text(sql), params or {})
    r = row.fetchone()
    return r[0] if r else None


async def apply_country_localization(
    env: Environment,
    company_id: int,
    country_code: str,
    *,
    confirm_currency_change: bool = False,
    extra_company_vals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply ``country_code``'s localization package to ``company_id``.

    ``extra_company_vals`` (e.g. ``{"lang": "en"}``) is folded into the single final
    ``res_company`` UPDATE so a Settings save stays atomic at the company-row level.

    Returns one of:
      * ``{"applied": False, "country": code}``                 — neutral country, only country_id set
      * ``{"applied": False, "warning": "currency_change_requires_confirmation", ...}``
                                                                — blocked, zero writes
      * ``{"applied": True, ...}``                              — package seeded + defaults switched
    """
    country_code = (country_code or "").upper()
    extra_company_vals = extra_company_vals or {}
    pack = get_pack(country_code)

    async with env.dml_conn() as conn:
        country_id = await _scalar(
            conn, "SELECT id FROM res_country WHERE code = :c", {"c": country_code}
        )
        if country_id is None:
            raise ValueError(f"Unknown country code: {country_code!r}")

        # --- Neutral country: no package -------------------------------------------------
        if pack is None:
            sets = {"country_id": country_id, **extra_company_vals}
            await _write_company(conn, company_id, sets)
            await conn.commit()
            _log.info(
                "localization: neutral country %s applied to company %s (no package)",
                country_code,
                company_id,
            )
            return {"applied": False, "country": country_code}

        # --- Currency-conflict pre-check (zero writes on the blocked path) --------------
        target_currency_code = pack["currency"]["code"]
        current_currency_code = await _scalar(
            conn,
            "SELECT c.code FROM res_currency c "
            "JOIN res_company co ON co.currency_id = c.id WHERE co.id = :id",
            {"id": company_id},
        )
        currency_changes = current_currency_code != target_currency_code
        if currency_changes and not confirm_currency_change:
            posted_lines = await _scalar(
                conn,
                "SELECT COUNT(*) FROM account_move_line l "
                "JOIN account_move m ON m.id = l.move_id WHERE m.state = 'posted'",
            )
            if posted_lines and int(posted_lines) > 0:
                _log.warning(
                    "localization: currency change %s->%s blocked for company %s "
                    "(%s posted lines) pending confirmation",
                    current_currency_code,
                    target_currency_code,
                    company_id,
                    posted_lines,
                )
                return {
                    "applied": False,
                    "warning": "currency_change_requires_confirmation",
                    "from": current_currency_code,
                    "to": target_currency_code,
                    "posted_lines": int(posted_lines),
                }

        summary: dict[str, Any] = {
            "applied": True,
            "country": country_code,
            "currency": target_currency_code,
            "currency_seeded": False,
            "taxes_created": 0,
            "taxes_reused": 0,
            "fiscal_positions_created": 0,
            "fiscal_positions_reused": 0,
            "archived_generic_taxes": 0,
        }

        # --- Currency ------------------------------------------------------------------
        currency_id = await _scalar(
            conn, "SELECT id FROM res_currency WHERE code = :c", {"c": target_currency_code}
        )
        if currency_id is None:
            cur = pack["currency"]
            currency_id = await _scalar(
                conn,
                "INSERT INTO res_currency (code, name, symbol, rounding, active) "
                "VALUES (:code, :name, :symbol, :rounding, TRUE) RETURNING id",
                {
                    "code": cur["code"],
                    "name": cur["name"],
                    "symbol": cur["symbol"],
                    "rounding": cur["rounding"],
                },
            )
            summary["currency_seeded"] = True
            _log.info("localization: seeded currency %s", target_currency_code)
        else:
            await conn.execute(
                text("UPDATE res_currency SET active = TRUE WHERE id = :id"),
                {"id": currency_id},
            )

        # --- Tax group ---------------------------------------------------------------
        group_id = await _scalar(
            conn,
            "SELECT id FROM account_tax_group WHERE company_id = :cid AND name = :n",
            {"cid": company_id, "n": pack["tax_group"]},
        )
        if group_id is None:
            group_id = await _scalar(
                conn,
                "INSERT INTO account_tax_group (name, sequence, company_id) "
                "VALUES (:n, 10, :cid) RETURNING id",
                {"n": pack["tax_group"], "cid": company_id},
            )

        # --- Taxes + repartition ---------------------------------------------------
        tax_ids: dict[str, int] = {}
        for tdef in pack["taxes"]:
            existing = await conn.execute(
                text(
                    "SELECT id, active FROM account_tax "
                    "WHERE company_id = :cid AND name = :n"
                ),
                {"cid": company_id, "n": tdef["name"]},
            )
            row = existing.fetchone()
            if row:
                tax_ids[tdef["key"]] = row[0]
                if not row[1]:
                    await conn.execute(
                        text("UPDATE account_tax SET active = TRUE WHERE id = :id"),
                        {"id": row[0]},
                    )
                summary["taxes_reused"] += 1
                continue

            tax_id = await _scalar(
                conn,
                "INSERT INTO account_tax "
                "(name, type_tax_use, amount_type, amount, price_include, "
                " include_base_amount, tax_group_id, company_id, active) "
                "VALUES (:n, :ttu, :at, :amt, FALSE, FALSE, :gid, :cid, TRUE) RETURNING id",
                {
                    "n": tdef["name"],
                    "ttu": tdef["type_tax_use"],
                    "at": tdef["amount_type"],
                    "amt": tdef["amount"],
                    "gid": group_id,
                    "cid": company_id,
                },
            )
            tax_ids[tdef["key"]] = tax_id
            summary["taxes_created"] += 1

            acct_id = None
            if tdef.get("tax_account_code"):
                acct_id = await _scalar(
                    conn,
                    "SELECT id FROM account_account "
                    "WHERE company_id = :cid AND code = :code",
                    {"cid": company_id, "code": tdef["tax_account_code"]},
                )
            for doc_type in ("invoice", "refund"):
                await conn.execute(
                    text(
                        "INSERT INTO account_tax_repartition_line "
                        "(tax_id, document_type, repartition_type, factor_percent, "
                        " account_id, sequence) "
                        "VALUES (:tid, :dt, 'base', 100, NULL, 1)"
                    ),
                    {"tid": tax_id, "dt": doc_type},
                )
                await conn.execute(
                    text(
                        "INSERT INTO account_tax_repartition_line "
                        "(tax_id, document_type, repartition_type, factor_percent, "
                        " account_id, sequence) "
                        "VALUES (:tid, :dt, 'tax', 100, :acct, 2)"
                    ),
                    {"tid": tax_id, "dt": doc_type, "acct": acct_id},
                )

        # --- Fiscal positions + tax maps ----------------------------------------
        fp_ids: dict[str, int] = {}
        for fpdef in pack["fiscal_positions"]:
            fp_id = await _scalar(
                conn,
                "SELECT id FROM account_fiscal_position "
                "WHERE company_id = :cid AND name = :n",
                {"cid": company_id, "n": fpdef["name"]},
            )
            if fp_id is None:
                fp_id = await _scalar(
                    conn,
                    "INSERT INTO account_fiscal_position (name, company_id, active) "
                    "VALUES (:n, :cid, TRUE) RETURNING id",
                    {"n": fpdef["name"], "cid": company_id},
                )
                summary["fiscal_positions_created"] += 1
            else:
                await conn.execute(
                    text(
                        "UPDATE account_fiscal_position SET active = TRUE WHERE id = :id"
                    ),
                    {"id": fp_id},
                )
                summary["fiscal_positions_reused"] += 1
            fp_ids[fpdef["name"]] = fp_id

            for tmap in fpdef["tax_maps"]:
                src_id = tax_ids.get(tmap["src"])
                dest_id = tax_ids.get(tmap["dest"])
                if src_id is None:
                    continue
                already = await _scalar(
                    conn,
                    "SELECT id FROM account_fiscal_position_tax "
                    "WHERE position_id = :pid AND tax_src_id = :src",
                    {"pid": fp_id, "src": src_id},
                )
                if already is None:
                    await conn.execute(
                        text(
                            "INSERT INTO account_fiscal_position_tax "
                            "(position_id, tax_src_id, tax_dest_id) "
                            "VALUES (:pid, :src, :dest)"
                        ),
                        {"pid": fp_id, "src": src_id, "dest": dest_id},
                    )

        # --- Archive superseded generic demo taxes (retain, never delete) -------
        for gname in pack.get("supersedes_tax_names", []):
            archived = await conn.execute(
                text(
                    "UPDATE account_tax SET active = FALSE "
                    "WHERE company_id = :cid AND name = :n AND active = TRUE "
                    "AND id NOT IN (SELECT DISTINCT tax_line_id FROM account_move_line "
                    "               WHERE tax_line_id IS NOT NULL) "
                    "RETURNING id"
                ),
                {"cid": company_id, "n": gname},
            )
            summary["archived_generic_taxes"] += len(archived.fetchall())

        # --- Company defaults (single UPDATE, includes extra vals) --------------
        defaults = pack["defaults"]
        sets = {
            "country_id": country_id,
            "currency_id": currency_id,
            "tax_label": pack["tax_label"],
            "tax_rounding_method": pack["tax_rounding_method"],
            "default_sale_tax_id": tax_ids.get(defaults["default_sale_tax_key"]),
            "default_purchase_tax_id": tax_ids.get(defaults["default_purchase_tax_key"]),
            "default_fiscal_position_id": fp_ids.get(defaults["default_fiscal_position"]),
            **extra_company_vals,
        }
        await _write_company(conn, company_id, sets)
        await conn.commit()

        summary["company_defaults"] = {
            "currency_id": currency_id,
            "tax_label": pack["tax_label"],
            "tax_rounding_method": pack["tax_rounding_method"],
            "default_sale_tax_id": sets["default_sale_tax_id"],
            "default_purchase_tax_id": sets["default_purchase_tax_id"],
            "default_fiscal_position_id": sets["default_fiscal_position_id"],
        }
        _log.info(
            "localization: applied %s package to company %s (%s)",
            country_code,
            company_id,
            summary,
        )
        return summary


async def _write_company(conn, company_id: int, sets: dict[str, Any]) -> None:
    if not sets:
        return
    assignments = ", ".join(f"{k} = :{k}" for k in sets)
    await conn.execute(
        text(f"UPDATE res_company SET {assignments}, write_date = now() WHERE id = :company_id"),
        {**sets, "company_id": company_id},
    )
