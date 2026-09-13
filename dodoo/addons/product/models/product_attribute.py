"""``product.attribute`` / ``product.attribute.value`` / ``product.template.attribute.line`` —
the taxonomy used to generate variants (FR-005)."""

from __future__ import annotations

from dodoo.core.fields import Char, Many2many, Many2one
from dodoo.core.models import BaseModel


class ProductAttribute(BaseModel):
    _name = "product.attribute"

    name = Char(size=64, required=True)


class ProductAttributeValue(BaseModel):
    _name = "product.attribute.value"

    attribute_id = Many2one("product.attribute", required=True)
    name = Char(size=64, required=True)


class ProductTemplateAttributeLine(BaseModel):
    _name = "product.template.attribute.line"

    template_id = Many2one("product.template", required=True)
    attribute_id = Many2one("product.attribute", required=True)
    value_ids = Many2many(
        "product.attribute.value",
        relation_table="product_template_attribute_line_value_rel",
        column1="line_id",
        column2="value_id",
    )
