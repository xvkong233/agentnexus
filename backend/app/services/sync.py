"""同步任务：发现并导入上游自建的会话（渠道 IM 入口、定时任务触发），维护状态。

归属逻辑：
1. 会话 metadata.tenant_id / metadata.source（平台创建时写入）
2. metadata.channel_id → 本地渠道 → 租户
3. deployment_runs → 本地定时任务 → 租户
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.crypto import decrypt_secret
from app.db import SessionLocal
from app.models import Channel, Deployment, PlatformKey, Session as SessionRow, Tenant
from app.services.bigmodel.mock import MockBigModelClient
from app.services.bigmodel.real import RealBigModelClient
from app.services.metering import parse_iso

logger = logging.getLogger("app.sync")

WINDOW_MINUTES = 15
MAX_PAGES = 5


async def _upsert_session(
    db: AsyncSession,
    tenant_id: str,
    up: dict,
    *,
    source: str,
    channel_id: str | None = None,
    deployment_id: str | None = None,
    agent_id: str | None = None,
) -> bool:
    """按 upstream_id 幂等导入/刷新。返回是否新建。"""
    upstream_id = up.get("id")
    if not upstream_id:
        return False
    existing = (
        await db.execute(select(SessionRow).where(SessionRow.upstream_id == upstream_id))
    ).scalar_one_or_none()
    agent = up.get("agent") or {}
    model = agent.get("model") or {}
    model_str = model.get("id") if isinstance(model, dict) else str(model)
    if existing:
        existing.status = up.get("status") or existing.status
        existing.upstream_updated_at = parse_iso(up.get("updated_at")) or existing.upstream_updated_at
        if up.get("archived_at") and not existing.archived_at:
            from app.models import utcnow

            existing.archived_at = utcnow()
        return False

    row = SessionRow(
        tenant_id=tenant_id,
        upstream_id=upstream_id,
        upstream_agent_id=agent.get("id") or "",
        upstream_env_id=up.get("environment_id") or "",
        title=up.get("title") or "",
        source=source,
        channel_id=channel_id,
        deployment_id=deployment_id,
        agent_id=agent_id,
        model_id=model_str or "",
        status=up.get("status") or "idle",
        upstream_updated_at=parse_iso(up.get("updated_at")),
        archived_at=parse_iso(up.get("archived_at")),
    )
    db.add(row)
    return True


async def _iter_session_pages(client, params: dict):
    page = None
    for _ in range(MAX_PAGES):
        p = dict(params)
        if page:
            p["page"] = page
        resp = await client.list_sessions(p)
        data = resp.get("data") or []
        for item in data:
            yield item
        page = resp.get("next_page")
        if not page or not data:
            return


async def sync_tick() -> int:
    """单轮同步。返回导入的新会话数。"""
    imported = 0
    try:
        async with SessionLocal() as db:
            # 平台密钥决定了上游组织范围：逐个 Key 扫描
            keys = (
                await db.execute(
                    select(PlatformKey).where(PlatformKey.status == "active").order_by(PlatformKey.is_default.desc())
                )
            ).scalars().all()

            since = (datetime.now(timezone.utc) - timedelta(minutes=WINDOW_MINUTES)).isoformat().replace("+00:00", "Z")
            for key in keys:
                if settings.bigmodel_mock:
                    client = MockBigModelClient()
                else:
                    client = RealBigModelClient(decrypt_secret(key.encrypted_key))
                try:
                    async for up in _iter_session_pages(client, {"created_at[gte]": since, "limit": 100}):
                        meta = up.get("metadata") or {}
                        tenant_id = meta.get("tenant_id") or ""
                        source = meta.get("source") or "imported"
                        channel_id = None
                        deployment_id = None
                        agent_id = None

                        if not tenant_id:
                            chan_meta = meta.get("channel_id")
                            if chan_meta:
                                chan = (
                                    await db.execute(
                                        select(Channel).where(Channel.upstream_id == chan_meta)
                                    )
                                ).scalar_one_or_none()
                                if chan:
                                    tenant_id = chan.tenant_id
                                    channel_id = chan.id
                                    source = "channel"
                            dep_meta = meta.get("deployment_id")
                            if dep_meta and not tenant_id:
                                dep = (
                                    await db.execute(
                                        select(Deployment).where(Deployment.upstream_id == dep_meta)
                                    )
                                ).scalar_one_or_none()
                                if dep:
                                    tenant_id = dep.tenant_id
                                    deployment_id = dep.id
                                    agent_id = dep.agent_id
                                    source = "deployment"

                        if not tenant_id:
                            logger.warning("会话 %s 无法归属租户，跳过", up.get("id"))
                            continue
                        tenant = await db.get(Tenant, tenant_id)
                        if not tenant:
                            continue

                        created = await _upsert_session(
                            db, tenant_id, up, source=source,
                            channel_id=channel_id, deployment_id=deployment_id, agent_id=agent_id,
                        )
                        imported += int(created)
                except Exception:
                    logger.exception("密钥 %s 同步会话失败", key.name)
                    await db.rollback()
                    continue

            # 定时任务链路：deployment_runs 兜底归属（上游不一定会话 metadata）
            deployments = (
                await db.execute(select(Deployment).where(Deployment.status != "archived"))
            ).scalars().all()
            for dep in deployments:
                client = await _client_for(db, dep.tenant_id)
                try:
                    runs_resp = await client.list_deployment_runs({"deployment_id": dep.upstream_id, "limit": 50})
                    for run in runs_resp.get("data") or []:
                        sid = run.get("session_id")
                        if not sid:
                            continue
                        exists = (
                            await db.execute(select(SessionRow.id).where(SessionRow.upstream_id == sid))
                        ).scalar_one_or_none()
                        if exists:
                            continue
                        try:
                            up = await client.get_session(sid)
                        except Exception:
                            continue
                        meta = up.get("metadata") or {}
                        tenant_id = meta.get("tenant_id") or dep.tenant_id
                        await _upsert_session(
                            db, tenant_id, up, source="deployment",
                            deployment_id=dep.id, agent_id=dep.agent_id,
                        )
                        imported += 1
                except Exception:
                    logger.exception("deployment_runs 同步失败: %s", dep.name)
                    await db.rollback()

            await db.commit()
    except Exception:
        logger.exception("同步任务异常")
    return imported


async def _client_for(db: AsyncSession, tenant_id: str):
    from app.services.bigmodel.factory import get_client_for_tenant

    return await get_client_for_tenant(db, tenant_id)
