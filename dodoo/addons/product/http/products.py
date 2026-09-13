"""REST action routes for the product catalog (US1): variant (re)generation, search, UoM
conversion. Plain CRUD on categories/UoM/templates/variants goes through JSON-RPC."""

from __future__ import annotations

from fastapi import Request

from dodoo.addons.product.http import json_err, json_ok
from dodoo.addons.product.validators import ApplyAttributeLines, and_domain, validate
from dodoo.core.exceptions import DodooError
from dodoo.http.routing import route


@route(
    "/product/template/{template_id}/attribute-lines/apply",
    methods=["POST"],
    auth="session",
)
async def apply_attribute_lines(request: Request, template_id: int):
    env = request.app.state.env
    try:
        payload = validate(ApplyAttributeLines, await request.json())
        from dodoo.addons.product.models.product_attribute import (
            ProductTemplateAttributeLine,
        )
        from dodoo.addons.product.models.product_product import ProductProduct

        existing_line_ids = await ProductTemplateAttributeLine.search(
            env, [["template_id", "=", template_id]]
        )
        if existing_line_ids:
            await ProductTemplateAttributeLine.unlink(env, existing_line_ids)
        for line in payload.lines:
            await ProductTemplateAttributeLine.create(
                env,
                {
                    "template_id": template_id,
                    "attribute_id": line.attribute_id,
                    "value_ids": line.value_ids,
                },
            )
        variant_ids = await ProductProduct.generate_variants(env, template_id)
        return json_ok({"template_id": template_id, "variant_ids": variant_ids})
    except DodooError as exc:
        return json_err(str(exc))


@route("/product/search", methods=["GET"], auth="session")
async def search_products(request: Request):
    env = request.app.state.env
    q = request.query_params.get("q")
    category_id = request.query_params.get("category_id")
    product_type = request.query_params.get("product_type")
    tracked_only = request.query_params.get("tracked_only")

    from dodoo.addons.product.models.product_product import ProductProduct
    from dodoo.addons.product.models.product_template import ProductTemplate

    domain: list = []
    if category_id:
        domain.append(["category_id", "=", int(category_id)])
    if product_type:
        domain.append(["product_type", "=", product_type])
    if tracked_only:
        domain.append(["is_storable", "=", True])

    template_ids = await ProductTemplate.search(env, and_domain(*domain) if domain else None)
    templates = {
        t["id"]: t
        for t in (
            await ProductTemplate.read(
                env,
                template_ids,
                ["name", "barcode", "category_id", "product_type", "is_storable"],
            )
            if template_ids
            else []
        )
    }
    variant_ids = (
        await ProductProduct.search(env, [["template_id", "in", template_ids]])
        if template_ids
        else []
    )
    variants = (
        await ProductProduct.read(env, variant_ids, ["template_id", "barcode"])
        if variant_ids
        else []
    )

    results = []
    for v in variants:
        t = templates.get(v["template_id"])
        if not t:
            continue
        name = t["name"]
        barcode = v["barcode"] or t["barcode"]
        if q and q.lower() not in name.lower() and (not barcode or q.lower() not in barcode.lower()):
            continue
        results.append(
            {
                "product_id": v["id"],
                "template_id": t["id"],
                "name": name,
                "barcode": barcode,
                "category_id": t["category_id"],
                "product_type": t["product_type"],
                "is_storable": t["is_storable"],
            }
        )
    return json_ok({"results": results})


@route("/product/{product_id}/uom-convert", methods=["GET"], auth="session")
async def uom_convert(request: Request, product_id: int):
    env = request.app.state.env
    try:
        qty = float(request.query_params.get("qty", "0"))
        to_uom_id = int(request.query_params["to_uom_id"])

        from dodoo.addons.product.models.product_product import ProductProduct
        from dodoo.addons.product.models.product_template import ProductTemplate
        from dodoo.addons.product.models.uom import UomUom

        variants = await ProductProduct.read(env, [product_id], ["template_id"])
        if not variants:
            return json_err("product_not_found", status_code=404)
        templates = await ProductTemplate.read(
            env, [variants[0]["template_id"]], ["uom_id"]
        )
        from_uom_id = templates[0]["uom_id"]
        converted = await UomUom.convert(env, qty, from_uom_id, to_uom_id)
        return json_ok({"qty": converted, "to_uom_id": to_uom_id})
    except DodooError as exc:
        return json_err(str(exc))
