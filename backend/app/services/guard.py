"""守护任务：欠费自动暂停定时任务，充值后自动恢复。"""
import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.models import Deployment, Tenant, Wallet
from app.services.bigmodel.factory import get_client_for_tenant
from app.services.billing import D

logger = logging.getLogger("app.guard")


async def _set_deployments_paused(db: AsyncSession, tenant_id: str, pause: bool) -> int:
    """暂停/恢复租户名下由守护任务控制的定时任务。返回处理数。"""
    if pause:
        stmt = select(Deployment).where(
            Deployment.tenant_id == tenant_id, Deployment.status == "active", Deployment.paused_by_guard.is_(False)
        )
    else:
        stmt = select(Deployment).where(
            Deployment.tenant_id == tenant_id, Deployment.paused_by_guard.is_(True)
        )
    rows = (await db.execute(stmt)).scalars().all()
    changed = 0
    for dep in rows:
        try:
            client = await get_client_for_tenant(db, tenant_id)
            if pause:
                await client.pause_deployment(dep.upstream_id)
                dep.status = "paused"
                dep.paused_by_guard = True
            else:
                if dep.status == "paused":
                    await client.unpause_deployment(dep.upstream_id)
                    dep.status = "active"
                dep.paused_by_guard = False
            changed += 1
        except Exception:
            logger.exception("deployment %s pause/unpause 失败", dep.upstream_id)
    return changed


async def guard_tick() -> int:
    changed = 0
    try:
        async with SessionLocal() as db:
            rows = (
                await db.execute(select(Wallet, Tenant).join(Tenant, Wallet.tenant_id == Tenant.id))
            ).all()
            for wallet, tenant in rows:
                threshold = D(tenant.low_balance_threshold or 0)
                should_block = D(wallet.balance) <= threshold
                if should_block and not wallet.blocked:
                    wallet.blocked = True
                    wallet.blocked_reason = f"余额不高于欠费阈值 ¥{threshold}，服务已自动暂停"
                    changed += await _set_deployments_paused(db, tenant.id, pause=True)
                    logger.info("租户 %s 欠费封锁，已暂停其定时任务", tenant.name)
                elif not should_block and wallet.blocked:
                    wallet.blocked = False
                    wallet.blocked_reason = ""
                    changed += await _set_deployments_paused(db, tenant.id, pause=False)
                    logger.info("租户 %s 余额恢复，解除封锁", tenant.name)
            await db.commit()
    except Exception:
        logger.exception("守护任务异常")
    return changed
