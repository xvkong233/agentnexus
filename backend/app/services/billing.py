"""计费引擎：定价计算、钱包扣费（行锁事务）、差值计量入账。

核心约定：
- 售价 = 官方成本价 × 加价率；计费时快照单价写入 usage_records，历史账单不受改价影响
- 上游 usage 为累计快照，本地保存上次快照做差值；差值只增不减，天然幂等
- 扣费在同一 DB 事务内完成：usage_record + wallet_transaction + wallet 更新
"""
import logging
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import insufficient_balance
from app.models import PricingRule, UsageRecord, Wallet, WalletTransaction, utcnow

logger = logging.getLogger("app.billing")

CENT = Decimal("0.000001")


def D(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def q6(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def effective_prices(rule: PricingRule | None) -> dict[str, Decimal]:
    """售价（元/百万 token、元/次搜索）。无规则时按 0 计，并留下待配置痕迹。"""
    if not rule:
        return {
            "input_per_m": Decimal("0"),
            "output_per_m": Decimal("0"),
            "cache_read_per_m": Decimal("0"),
            "web_search_per_call": Decimal("0"),
        }
    markup = D(rule.markup_rate or 1)
    return {
        "input_per_m": D(rule.cost_input_per_m) * markup,
        "output_per_m": D(rule.cost_output_per_m) * markup,
        "cache_read_per_m": D(rule.cost_cache_read_per_m) * markup,
        "web_search_per_call": D(rule.web_search_price_per_call),
    }


def compute_costs(
    delta_input: int,
    delta_output: int,
    delta_cache_read: int,
    delta_search: int,
    rule: PricingRule | None,
) -> dict:
    """按差值计算各项费用（Decimal，6 位小数）。"""
    prices = effective_prices(rule)
    million = Decimal("1000000")
    cost_input = q6(prices["input_per_m"] * delta_input / million)
    cost_output = q6(prices["output_per_m"] * delta_output / million)
    cost_cache = q6(prices["cache_read_per_m"] * delta_cache_read / million)
    cost_search = q6(prices["web_search_per_call"] * delta_search)
    total = q6(cost_input + cost_output + cost_cache + cost_search)
    return {
        "prices": prices,
        "cost_input": cost_input,
        "cost_output": cost_output,
        "cost_cache": cost_cache,
        "cost_search": cost_search,
        "cost_total": total,
    }


async def get_wallet(db: AsyncSession, tenant_id: str, for_update: bool = False) -> Wallet:
    stmt = select(Wallet).where(Wallet.tenant_id == tenant_id)
    if for_update:
        stmt = stmt.with_for_update()
    wallet = (await db.execute(stmt)).scalar_one_or_none()
    if not wallet:
        wallet = Wallet(tenant_id=tenant_id, balance=0, blocked=False)
        db.add(wallet)
        await db.flush()
    return wallet


async def ensure_can_spend(db: AsyncSession, tenant_id: str, threshold: Decimal | None = None) -> Wallet:
    """发消息/建会话前的余额门槛校验。"""
    wallet = await get_wallet(db, tenant_id)
    if wallet.blocked:
        raise insufficient_balance(wallet.blocked_reason or "账户已被停用")
    from sqlalchemy import select as _s
    from app.models import Tenant

    tenant = (await db.execute(_s(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    floor = D(threshold if threshold is not None else (tenant.low_balance_threshold if tenant else 0))
    if D(wallet.balance) <= floor:
        raise insufficient_balance()
    return wallet


async def wallet_op(
    db: AsyncSession,
    tenant_id: str,
    op_type: str,
    amount: Decimal,
    operator: str = "system",
    note: str = "",
    ref_type: str = "",
    ref_id: str = "",
) -> Wallet:
    """钱包变动（recharge/adjust/refund/consumption），行锁 + 流水。"""
    wallet = await get_wallet(db, tenant_id, for_update=True)
    new_balance = q6(D(wallet.balance) + D(amount))
    wallet.balance = new_balance
    db.add(
        WalletTransaction(
            tenant_id=tenant_id,
            type=op_type,
            amount=q6(D(amount)),
            balance_after=new_balance,
            ref_type=ref_type,
            ref_id=ref_id,
            note=note,
            operator=operator,
        )
    )
    await db.flush()
    return wallet


async def apply_usage_delta(
    db: AsyncSession,
    session_row,
    up_usage: dict,
    rule: PricingRule | None,
    source: str | None = None,
) -> UsageRecord | None:
    """上游累计快照 vs 本地缓存 → 差值入账。返回计费流水（无差值返回 None）。

    调用方负责 commit。金额为负/回退的情况按 0 处理（上游快照理论上单调递增）。
    """
    up_in = int(up_usage.get("input_tokens") or 0)
    up_out = int(up_usage.get("output_tokens") or 0)
    up_cache = int(up_usage.get("cache_read_input_tokens") or 0)
    server_tool = up_usage.get("server_tool_use") or {}
    up_search = int(server_tool.get("web_search_requests") or 0)

    delta_in = max(0, up_in - int(session_row.usage_input or 0))
    delta_out = max(0, up_out - int(session_row.usage_output or 0))
    delta_cache = max(0, up_cache - int(session_row.usage_cache_read or 0))
    delta_search = max(0, up_search - int(session_row.usage_web_search or 0))

    costs = compute_costs(delta_in, delta_out, delta_cache, delta_search, rule)
    record: UsageRecord | None = None

    if costs["cost_total"] > 0 or (delta_in + delta_out + delta_cache + delta_search) > 0:
        record = UsageRecord(
            tenant_id=session_row.tenant_id,
            session_id=session_row.id,
            upstream_session_id=session_row.upstream_id,
            model_id=session_row.model_id or "unknown",
            source=source or session_row.source,
            input_tokens=delta_in,
            output_tokens=delta_out,
            cache_read_tokens=delta_cache,
            web_search_requests=delta_search,
            cost_input=float(costs["cost_input"]),
            cost_output=float(costs["cost_output"]),
            cost_cache=float(costs["cost_cache"]),
            cost_search=float(costs["cost_search"]),
            cost_total=float(costs["cost_total"]),
            price_snapshot={
                "input_per_m": str(costs["prices"]["input_per_m"]),
                "output_per_m": str(costs["prices"]["output_per_m"]),
                "cache_read_per_m": str(costs["prices"]["cache_read_per_m"]),
                "web_search_per_call": str(costs["prices"]["web_search_per_call"]),
            },
        )
        db.add(record)

    session_row.usage_input = max(int(session_row.usage_input or 0), up_in)
    session_row.usage_output = max(int(session_row.usage_output or 0), up_out)
    session_row.usage_cache_read = max(int(session_row.usage_cache_read or 0), up_cache)
    session_row.usage_web_search = max(int(session_row.usage_web_search or 0), up_search)

    if record is not None and costs["cost_total"] > 0:
        await wallet_op(
            db,
            session_row.tenant_id,
            "consumption",
            -costs["cost_total"],
            operator="metering",
            note=f"会话 {session_row.upstream_id} 用量扣费",
            ref_type="usage_record",
            ref_id=record.id,
        )
        session_row.cost_total = q6(D(session_row.cost_total or 0) + costs["cost_total"])

    session_row.last_metered_at = utcnow()
    await db.flush()
    return record
