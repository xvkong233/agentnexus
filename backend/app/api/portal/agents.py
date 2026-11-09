"""客户 Agent 管理：CRUD（镜像上游）+ 版本列表。"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession, require_tenant_user
from app.core.errors import not_found
from app.models import Agent
from app.services.agentops import build_agent_payload
from app.services.bigmodel.factory import get_client_for_tenant

router = APIRouter(dependencies=[Depends(require_tenant_user)])


class AgentBody(BaseModel):
    name: str | None = None
    model: str | dict | None = None
    system: str | None = None
    description: str | None = None
    tools: list | None = None
    mcp_servers: list | None = None
    skills: list | None = None


def _view(a: Agent) -> dict:
    return {
        "id": a.id,
        "upstream_id": a.upstream_id,
        "name": a.name,
        "description": a.description,
        "model_id": a.model_id,
        "model": a.model_config_json,
        "system": a.system,
        "tools": a.tools,
        "mcp_servers": a.mcp_servers,
        "skills": a.skills,
        "version": a.upstream_version,
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


async def _sync_local(db, row: Agent, up: dict) -> None:
    model = up.get("model") or {}
    row.name = up.get("name") or row.name
    row.description = up.get("description") or ""
    row.model_config_json = model
    row.model_id = model.get("id") if isinstance(model, dict) else str(model)
    row.system = up.get("system") or ""
    row.tools = up.get("tools") or []
    row.mcp_servers = up.get("mcp_servers") or []
    row.skills = up.get("skills") or []
    row.upstream_version = up.get("version") or row.upstream_version
    row.status = "archived" if up.get("archived_at") else "active"


@router.get("/agents")
async def list_agents(request: Request, db: DbSession, include_archived: bool = False):
    stmt = (
        select(Agent)
        .where(Agent.tenant_id == request.state.tenant_id)
        .order_by(Agent.created_at.desc())
    )
    if not include_archived:
        stmt = stmt.where(Agent.status == "active")
    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [_view(a) for a in rows]}


@router.post("/agents")
async def create_agent(body: AgentBody, request: Request, db: DbSession):
    payload = build_agent_payload(body.model_dump())
    if "name" not in payload:
        from app.core.errors import bad_request

        raise bad_request("name 必填")
    client = await get_client_for_tenant(db, request.state.tenant_id)
    up = await client.create_agent(payload)
    model = up.get("model") or {}
    row = Agent(
        tenant_id=request.state.tenant_id,
        upstream_id=up["id"],
        name=up.get("name") or "unnamed",
        description=up.get("description") or "",
        model_config_json=model,
        model_id=model.get("id") if isinstance(model, dict) else str(model),
        system=up.get("system") or "",
        tools=up.get("tools") or [],
        mcp_servers=up.get("mcp_servers") or [],
        skills=up.get("skills") or [],
        upstream_version=up.get("version") or 1,
    )
    db.add(row)
    await db.commit()
    return _view(row)


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, request: Request, db: DbSession):
    row = await db.get(Agent, agent_id)
    if not row or row.tenant_id != request.state.tenant_id:
        raise not_found("Agent 不存在")
    return _view(row)


@router.post("/agents/{agent_id}")
async def update_agent(agent_id: str, body: AgentBody, request: Request, db: DbSession):
    row = await db.get(Agent, agent_id)
    if not row or row.tenant_id != request.state.tenant_id:
        raise not_found("Agent 不存在")
    payload = build_agent_payload(body.model_dump(exclude_none=True))
    client = await get_client_for_tenant(db, request.state.tenant_id)
    up = await client.update_agent(row.upstream_id, payload)
    await _sync_local(db, row, up)
    await db.commit()
    return _view(row)


@router.get("/agents/{agent_id}/versions")
async def agent_versions(agent_id: str, request: Request, db: DbSession):
    row = await db.get(Agent, agent_id)
    if not row or row.tenant_id != request.state.tenant_id:
        raise not_found("Agent 不存在")
    client = await get_client_for_tenant(db, request.state.tenant_id)
    return await client.list_agent_versions(row.upstream_id, {"limit": 100})


@router.post("/agents/{agent_id}/archive")
async def archive_agent(agent_id: str, request: Request, db: DbSession):
    row = await db.get(Agent, agent_id)
    if not row or row.tenant_id != request.state.tenant_id:
        raise not_found("Agent 不存在")
    client = await get_client_for_tenant(db, request.state.tenant_id)
    await client.archive_agent(row.upstream_id)
    row.status = "archived"
    await db.commit()
    return {"ok": True}
