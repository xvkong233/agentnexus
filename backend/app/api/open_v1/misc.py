"""Open API：钱包 / 用量 / Agent 与环境只读列表 / 定时任务简版。"""
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.common import paginate
from app.core.deps import DbSession
from app.core.errors import bad_request, not_found
from app.models import (
    Agent,
    Deployment,
    Environment,
    UsageRecord,
    Wallet,
)
from app.services.billing import ensure_can_spend
from app.services.bigmodel.factory import get_client_for_tenant

router = APIRouter()


def _tenant_id(request) -> str:
    return request.state.tenant_id


@router.get("/wallet")
async def wallet(request: Request, db: DbSession):
    w = await db.get(Wallet, _tenant_id(request))
    return {
        "balance": float(w.balance) if w else 0,
        "blocked": bool(w.blocked) if w else False,
        "blocked_reason": w.blocked_reason if w else "",
    }


@router.get("/usage/records")
async def usage_records(
    request: Request, db: DbSession, model_id: str = "", source: str = "",
    start: str = "", end: str = "", page: int = 1, page_size: int = 50,
):
    stmt = (
        select(UsageRecord)
        .where(UsageRecord.tenant_id == _tenant_id(request))
        .order_by(UsageRecord.created_at.desc())
    )
    if model_id:
        stmt = stmt.where(UsageRecord.model_id == model_id)
    if source:
        stmt = stmt.where(UsageRecord.source == source)
    if start:
        stmt = stmt.where(UsageRecord.created_at >= datetime.fromisoformat(start))
    if end:
        stmt = stmt.where(UsageRecord.created_at <= datetime.fromisoformat(end))
    rows, total = await paginate(db, stmt, page, page_size)
    return {
        "items": [
            {
                "id": r.id, "session_id": r.session_id, "model_id": r.model_id, "source": r.source,
                "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
                "cache_read_tokens": r.cache_read_tokens, "web_search_requests": r.web_search_requests,
                "cost_total": float(r.cost_total), "price_snapshot": r.price_snapshot,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/usage/summary")
async def usage_summary(request: Request, db: DbSession, month: str = ""):
    now = datetime.now(timezone.utc)
    if month and len(month) >= 7:
        year, m = int(month[:4]), int(month[5:7])
    else:
        year, m = now.year, now.month
    start = datetime(year, m, 1, tzinfo=timezone.utc)
    nxt_year, nxt_m = (year + 1, 1) if m == 12 else (year, m + 1)
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(UsageRecord.cost_total), 0),
                func.coalesce(func.sum(UsageRecord.input_tokens), 0),
                func.coalesce(func.sum(UsageRecord.output_tokens), 0),
                func.coalesce(func.sum(UsageRecord.cache_read_tokens), 0),
                func.coalesce(func.sum(UsageRecord.web_search_requests), 0),
            ).where(
                UsageRecord.tenant_id == _tenant_id(request),
                UsageRecord.created_at >= start,
                UsageRecord.created_at < datetime(nxt_year, nxt_m, 1, tzinfo=timezone.utc),
            )
        )
    ).one()
    return {
        "month": f"{year:04d}-{m:02d}",
        "cost": float(row[0]), "input_tokens": int(row[1]), "output_tokens": int(row[2]),
        "cache_read_tokens": int(row[3]), "web_search_requests": int(row[4]),
    }


@router.get("/agents")
async def list_agents(request: Request, db: DbSession):
    rows = (
        await db.execute(
            select(Agent).where(Agent.tenant_id == _tenant_id(request), Agent.status == "active")
        )
    ).scalars().all()
    return {
        "items": [
            {"id": a.id, "name": a.name, "model_id": a.model_id, "version": a.upstream_version,
             "description": a.description}
            for a in rows
        ]
    }


@router.get("/environments")
async def list_environments(request: Request, db: DbSession):
    rows = (
        await db.execute(
            select(Environment)
            .where(Environment.tenant_id == _tenant_id(request), Environment.status == "active")
        )
    ).scalars().all()
    return {"items": [{"id": e.id, "name": e.name, "config": e.config} for e in rows]}


# ---------- 定时任务（简版） ----------


class DeploymentBody(BaseModel):
    agent_id: str
    environment_id: str
    name: str
    schedule: dict | None = None
    initial_message: str | None = None
    initial_events: list | None = None


@router.get("/deployments")
async def list_deployments(request: Request, db: DbSession):
    rows = (
        await db.execute(
            select(Deployment)
            .where(Deployment.tenant_id == _tenant_id(request))
            .order_by(Deployment.created_at.desc())
        )
    ).scalars().all()
    return {
        "items": [
            {"id": d.id, "name": d.name, "agent_id": d.agent_id, "schedule": d.schedule,
             "status": d.status, "paused_by_guard": d.paused_by_guard}
            for d in rows
        ]
    }


@router.post("/deployments")
async def create_deployment(body: DeploymentBody, request: Request, db: DbSession):
    """创建定时任务。余额校验后即时生效。"""
    await ensure_can_spend(db, _tenant_id(request))
    agent = await db.get(Agent, body.agent_id)
    if not agent or agent.tenant_id != _tenant_id(request) or agent.status != "active":
        raise not_found("Agent 不存在或不可用")
    env = await db.get(Environment, body.environment_id)
    if not env or env.tenant_id != _tenant_id(request) or env.status != "active":
        raise not_found("运行环境不存在或不可用")
    if body.schedule and (body.schedule.get("type") != "cron" or not body.schedule.get("expression")):
        raise bad_request("schedule 须为 {type:'cron', expression:'...', timezone:'Asia/Shanghai'} 或 null")
    initial_events = body.initial_events
    if not initial_events and body.initial_message:
        initial_events = [{"type": "user.message", "content": [{"type": "text", "text": body.initial_message}]}]
    if not initial_events:
        raise bad_request("initial_message 或 initial_events 必填")

    client = await get_client_for_tenant(db, _tenant_id(request))
    payload: dict = {
        "name": body.name[:256],
        "agent": {"type": "agent", "id": agent.upstream_id, "version": agent.upstream_version},
        "environment_id": env.upstream_id,
        "initial_events": initial_events,
    }
    if body.schedule:
        payload["schedule"] = body.schedule
    up = await client.create_deployment(payload)
    row = Deployment(
        tenant_id=_tenant_id(request),
        upstream_id=up["id"],
        agent_id=agent.id,
        upstream_env_id=env.upstream_id,
        name=up.get("name") or body.name,
        schedule=up.get("schedule"),
        initial_events=initial_events,
        status=up.get("status") or "active",
    )
    db.add(row)
    await db.commit()
    return {"id": row.id, "upstream_id": row.upstream_id, "name": row.name, "status": row.status,
            "schedule": row.schedule}


@router.post("/deployments/{deployment_id}/pause")
async def pause(deployment_id: str, request: Request, db: DbSession):
    row = await db.get(Deployment, deployment_id)
    if not row or row.tenant_id != _tenant_id(request):
        raise not_found("定时任务不存在")
    client = await get_client_for_tenant(db, _tenant_id(request))
    await client.pause_deployment(row.upstream_id)
    row.status = "paused"
    row.paused_by_guard = False
    await db.commit()
    return {"ok": True}


@router.post("/deployments/{deployment_id}/unpause")
async def unpause(deployment_id: str, request: Request, db: DbSession):
    row = await db.get(Deployment, deployment_id)
    if not row or row.tenant_id != _tenant_id(request):
        raise not_found("定时任务不存在")
    await ensure_can_spend(db, _tenant_id(request))
    client = await get_client_for_tenant(db, _tenant_id(request))
    await client.unpause_deployment(row.upstream_id)
    row.status = "active"
    row.paused_by_guard = False
    await db.commit()
    return {"ok": True}


@router.post("/deployments/{deployment_id}/run")
async def run_once(deployment_id: str, request: Request, db: DbSession):
    row = await db.get(Deployment, deployment_id)
    if not row or row.tenant_id != _tenant_id(request):
        raise not_found("定时任务不存在")
    await ensure_can_spend(db, _tenant_id(request))
    client = await get_client_for_tenant(db, _tenant_id(request))
    result = await client.run_deployment(row.upstream_id)
    await db.commit()
    return result
