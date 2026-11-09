"""定价规则管理。"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession, require_admin
from app.core.errors import not_found
from app.models import PricingRule
from app.services.audit import write_audit
from app.services.billing import effective_prices

router = APIRouter(dependencies=[Depends(require_admin)])


class PricingBody(BaseModel):
    cost_input_per_m: float | None = None
    cost_output_per_m: float | None = None
    cost_cache_read_per_m: float | None = None
    markup_rate: float | None = None
    web_search_price_per_call: float | None = None
    note: str | None = None


def _view(rule: PricingRule) -> dict:
    prices = effective_prices(rule)
    return {
        "id": rule.id,
        "model_id": rule.model_id,
        "cost_input_per_m": float(rule.cost_input_per_m),
        "cost_output_per_m": float(rule.cost_output_per_m),
        "cost_cache_read_per_m": float(rule.cost_cache_read_per_m),
        "markup_rate": float(rule.markup_rate),
        "web_search_price_per_call": float(rule.web_search_price_per_call),
        "note": rule.note,
        "updated_by": rule.updated_by,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        # 展示用：当前生效售价（元/百万 token）
        "sale_input_per_m": float(prices["input_per_m"]),
        "sale_output_per_m": float(prices["output_per_m"]),
        "sale_cache_read_per_m": float(prices["cache_read_per_m"]),
        "sale_web_search_per_call": float(prices["web_search_per_call"]),
    }


@router.get("/pricing")
async def list_pricing(db: DbSession):
    rules = (await db.execute(select(PricingRule).order_by(PricingRule.model_id))).scalars().all()
    return {"items": [_view(r) for r in rules]}


@router.put("/pricing/{model_id}")
async def update_pricing(model_id: str, body: PricingBody, request: Request, db: DbSession):
    rule = (
        await db.execute(select(PricingRule).where(PricingRule.model_id == model_id))
    ).scalar_one_or_none()
    if not rule:
        raise not_found("定价规则不存在")
    if body.cost_input_per_m is not None:
        rule.cost_input_per_m = body.cost_input_per_m
    if body.cost_output_per_m is not None:
        rule.cost_output_per_m = body.cost_output_per_m
    if body.cost_cache_read_per_m is not None:
        rule.cost_cache_read_per_m = body.cost_cache_read_per_m
    if body.markup_rate is not None:
        rule.markup_rate = body.markup_rate
    if body.web_search_price_per_call is not None:
        rule.web_search_price_per_call = body.web_search_price_per_call
    if body.note is not None:
        rule.note = body.note
    rule.updated_by = request.state.actor[2]
    await write_audit(db, request, "pricing.update", "pricing_rule", model_id, body.model_dump(exclude_none=True))
    await db.commit()
    return _view(rule)
