"""计量服务：轮询兜底 + 查询即对账（实时结算差值）。

上游 usage 为累计快照；本地保存上次快照做差值计费。
- 查询路径（portal/open/admin 会话详情）调用 reconcile_live 实时结算
- metering_tick 周期兜底，覆盖无人查询的会话（渠道/定时任务产生的会话）
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.models import PricingRule, Session as SessionRow
from app.services.bigmodel.factory import get_client_for_tenant
from app.services.billing import apply_usage_delta

logger = logging.getLogger("app.metering")

BATCH = 200


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


async def apply_upstream(db: AsyncSession, row: SessionRow, up: dict) -> None:
    """把上游会话快照落到本地（行须已锁定）：状态同步 + 差值计费。"""
    new_status = up.get("status")
    if new_status:
        row.status = new_status
    if up.get("archived_at") and not row.archived_at:
        from app.models import utcnow

        row.archived_at = utcnow()
    up_updated = parse_iso(up.get("updated_at"))
    if up_updated:
        row.upstream_updated_at = up_updated

    rule = None
    model = (up.get("agent") or {}).get("model") or {}
    model_str = model.get("id") if isinstance(model, dict) else str(model)
    if model_str:
        if model_str != row.model_id:
            row.model_id = model_str
        rule = (
            await db.execute(select(PricingRule).where(PricingRule.model_id == model_str))
        ).scalar_one_or_none()

    await apply_usage_delta(db, row, up.get("usage") or {}, rule)


async def _locked_row(db: AsyncSession, row_id: str) -> SessionRow | None:
    stmt = select(SessionRow).where(SessionRow.id == row_id).with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def reconcile_live(db: AsyncSession, row: SessionRow, client=None) -> None:
    """查询即对账：拉上游详情并实时结算（差值计费+扣款）。失败静默（轮询兜底）。"""
    try:
        if client is None:
            client = await get_client_for_tenant(db, row.tenant_id)
        up = await client.get_session(row.upstream_id)
    except Exception:
        return
    try:
        locked = await _locked_row(db, row.id)
        if locked is None:
            return
        await apply_upstream(db, locked, up)
    except Exception:
        logger.exception("实时对账失败: %s", row.upstream_id)


async def meter_session(db: AsyncSession, row: SessionRow) -> None:
    client = await get_client_for_tenant(db, row.tenant_id)
    up = await client.get_session(row.upstream_id)
    locked = await _locked_row(db, row.id)
    if locked is None:
        return
    await apply_upstream(db, locked, up)


async def metering_tick() -> int:
    """单轮兜底计量。返回处理会话数。"""
    processed = 0
    try:
        async with SessionLocal() as db:
            stmt = (
                select(SessionRow)
                .where(
                    SessionRow.status.in_(["running", "rescheduling", "idle"]),
                    SessionRow.archived_at.is_(None),
                )
                .order_by(SessionRow.last_metered_at.asc().nulls_first())
                .limit(BATCH)
            )
            rows = (await db.execute(stmt)).scalars().all()
            for row in rows:
                try:
                    await meter_session(db, row)
                    processed += 1
                except Exception:
                    logger.exception("会话计量失败: %s", row.upstream_id)
                    await db.rollback()
                    continue
            await db.commit()
    except Exception:
        logger.exception("计量任务异常")
    return processed
