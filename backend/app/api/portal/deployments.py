"""客户定时任务（Deployments）：CRUD + 手动触发 + 运行记录。"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession, require_tenant_user
from app.core.errors import bad_request, not_found
from app.models import Agent, Deployment, Environment
from app.services.bigmodel.factory import get_client_for_tenant

router = APIRouter(dependencies=[Depends(require_tenant_user)])


def _tenant_id(request) -> str:
    return request.state.tenant_id


async def _own(db, request, deployment_id: str) -> Deployment:
    row = await db.get(Deployment, deployment_id)
    if not row or row.tenant_id != _tenant_id(request):
        raise not_found("定时任务不存在")
    return row


def _view(d: Deployment, agent_name: str = "") -> dict:
    return {
        "id": d.id,
        "upstream_id": d.upstream_id,
        "agent_id": d.agent_id,
        "agent_name": agent_name,
        "name": d.name,
        "schedule": d.schedule,
        "initial_events": d.initial_events,
        "status": d.status,
        "paused_by_guard": d.paused_by_guard,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


class DeploymentBody(BaseModel):
    agent_id: str
    environment_id: str
    name: str
    schedule: dict | None = None       # {"type":"cron","expression":"0 9 * * 1-5","timezone":"Asia/Shanghai"} 或 null=手动
    initial_message: str | None = None
    initial_events: list | None = None


async def _build_payload(db, request, body: DeploymentBody) -> tuple[dict, Agent, Environment]:
    agent = await db.get(Agent, body.agent_id)
    if not agent or agent.tenant_id != _tenant_id(request) or agent.status != "active":
        raise not_found("Agent 不存在或不可用")
    env = await db.get(Environment, body.environment_id)
    if not env or env.tenant_id != _tenant_id(request) or env.status != "active":
        raise not_found("运行环境不存在或不可用")
    if body.schedule:
        if body.schedule.get("type") != "cron" or not body.schedule.get("expression"):
            raise bad_request("schedule 须为 {type:'cron', expression:'...', timezone:'Asia/Shanghai'} 或 null")
    initial_events = body.initial_events
    if not initial_events and body.initial_message:
        initial_events = [{"type": "user.message", "content": [{"type": "text", "text": body.initial_message}]}]
    if not initial_events:
        raise bad_request("initial_message 或 initial_events 必填（任务触发时的初始指令）")
    payload = {
        "name": body.name[:256],
        "agent": {"type": "agent", "id": agent.upstream_id, "version": agent.upstream_version},
        "environment_id": env.upstream_id,
        "initial_events": initial_events,
    }
    if body.schedule:
        payload["schedule"] = body.schedule
    return payload, agent, env


@router.get("/deployments")
async def list_deployments(request: Request, db: DbSession):
    rows = (
        await db.execute(
            select(Deployment)
            .where(Deployment.tenant_id == _tenant_id(request))
            .order_by(Deployment.created_at.desc())
        )
    ).scalars().all()
    names = {}
    if rows:
        arows = (await db.execute(select(Agent).where(Agent.id.in_({r.agent_id for r in rows})))).scalars().all()
        names = {a.id: a.name for a in arows}
    return {"items": [_view(d, names.get(d.agent_id, "")) for d in rows]}


@router.post("/deployments")
async def create_deployment(body: DeploymentBody, request: Request, db: DbSession):
    payload, agent, env = await _build_payload(db, request, body)
    client = await get_client_for_tenant(db, _tenant_id(request))
    up = await client.create_deployment(payload)
    row = Deployment(
        tenant_id=_tenant_id(request),
        upstream_id=up["id"],
        agent_id=agent.id,
        upstream_env_id=env.upstream_id,
        name=up.get("name") or body.name,
        schedule=up.get("schedule"),
        initial_events=body.initial_events or [],
        status=up.get("status") or "active",
    )
    db.add(row)
    await db.commit()
    return _view(row, agent.name)


@router.get("/deployments/{deployment_id}")
async def get_deployment(deployment_id: str, request: Request, db: DbSession):
    row = await _own(db, request, deployment_id)
    agent = await db.get(Agent, row.agent_id)
    return _view(row, agent.name if agent else "")


@router.post("/deployments/{deployment_id}")
async def update_deployment(deployment_id: str, body: DeploymentBody, request: Request, db: DbSession):
    row = await _own(db, request, deployment_id)
    payload, _agent, _env = await _build_payload(db, request, body)
    client = await get_client_for_tenant(db, _tenant_id(request))
    up = await client.update_deployment(row.upstream_id, payload)
    row.name = up.get("name") or row.name
    row.schedule = up.get("schedule")
    row.initial_events = body.initial_events or row.initial_events
    await db.commit()
    return _view(row)


@router.post("/deployments/{deployment_id}/pause")
async def pause(deployment_id: str, request: Request, db: DbSession):
    row = await _own(db, request, deployment_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    await client.pause_deployment(row.upstream_id)
    row.status = "paused"
    row.paused_by_guard = False
    await db.commit()
    return {"ok": True}


@router.post("/deployments/{deployment_id}/unpause")
async def unpause(deployment_id: str, request: Request, db: DbSession):
    row = await _own(db, request, deployment_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    await client.unpause_deployment(row.upstream_id)
    row.status = "active"
    row.paused_by_guard = False
    await db.commit()
    return {"ok": True}


@router.post("/deployments/{deployment_id}/archive")
async def archive(deployment_id: str, request: Request, db: DbSession):
    row = await _own(db, request, deployment_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    await client.archive_deployment(row.upstream_id)
    row.status = "archived"
    await db.commit()
    return {"ok": True}


@router.post("/deployments/{deployment_id}/run")
async def run_once(deployment_id: str, request: Request, db: DbSession):
    row = await _own(db, request, deployment_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    result = await client.run_deployment(row.upstream_id)
    await db.commit()
    return result


@router.get("/deployments/{deployment_id}/runs")
async def list_runs(deployment_id: str, request: Request, db: DbSession):
    row = await _own(db, request, deployment_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    return await client.list_deployment_runs({"deployment_id": row.upstream_id, "limit": 50})
