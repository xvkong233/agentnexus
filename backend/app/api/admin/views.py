"""管理端只读视图：全局会话 / Agent / 审计日志，及会话运维操作。"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.api.common import paginate
from app.core.deps import DbSession, require_admin
from app.core.errors import not_found
from app.models import Agent, AuditLog, Session as SessionRow, Tenant
from app.services.agentops import session_view
from app.services.audit import write_audit
from app.services.bigmodel.factory import get_client_for_tenant

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/sessions")
async def list_sessions(
    db: DbSession, tenant_id: str = "", status: str = "", source: str = "",
    keyword: str = "", page: int = 1, page_size: int = 20,
):
    stmt = select(SessionRow).order_by(SessionRow.created_at.desc())
    if tenant_id:
        stmt = stmt.where(SessionRow.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(SessionRow.status == status)
    if source:
        stmt = stmt.where(SessionRow.source == source)
    if keyword:
        stmt = stmt.where(SessionRow.title.like(f"%{keyword}%") | SessionRow.upstream_id.like(f"%{keyword}%"))
    rows, total = await paginate(db, stmt, page, page_size)
    tenants = {}
    if rows:
        trows = (await db.execute(select(Tenant).where(Tenant.id.in_({r.tenant_id for r in rows})))).scalars().all()
        tenants = {t.id: t.name for t in trows}
    items = []
    for r in rows:
        v = session_view(r)
        v["tenant_name"] = tenants.get(r.tenant_id, "")
        items.append(v)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, db: DbSession):
    row = await db.get(SessionRow, session_id)
    if not row:
        raise not_found("会话不存在")
    try:
        client = await get_client_for_tenant(db, row.tenant_id)
        up = await client.get_session(row.upstream_id)
        from app.services.metering import reconcile_live

        await reconcile_live(db, row, client)
        await db.commit()
        up = None
    except Exception:
        await db.rollback()
        try:
            await db.refresh(row)
        except Exception:
            pass
    return session_view(row)


class SessionOpBody(BaseModel):
    action: str  # archive / delete


@router.post("/sessions/{session_id}/ops")
async def session_ops(session_id: str, body: SessionOpBody, request: Request, db: DbSession):
    row = await db.get(SessionRow, session_id)
    if not row:
        raise not_found("会话不存在")
    client = await get_client_for_tenant(db, row.tenant_id)
    result: dict
    if body.action == "archive":
        result = await client.archive_session(row.upstream_id)
        from app.models import utcnow

        row.archived_at = utcnow()
        action = "session.archive"
    elif body.action == "delete":
        result = await client.delete_session(row.upstream_id)
        await db.delete(row)
        action = "session.delete"
    else:
        raise not_found("不支持的操作")
    await write_audit(db, request, action, "session", session_id, {"action": body.action})
    await db.commit()
    return {"ok": True, "result": result}


@router.get("/agents")
async def list_agents(db: DbSession, tenant_id: str = "", page: int = 1, page_size: int = 50):
    stmt = select(Agent).order_by(Agent.created_at.desc())
    if tenant_id:
        stmt = stmt.where(Agent.tenant_id == tenant_id)
    rows, total = await paginate(db, stmt, page, page_size)
    tenants = {}
    if rows:
        trows = (await db.execute(select(Tenant).where(Tenant.id.in_({r.tenant_id for r in rows})))).scalars().all()
        tenants = {t.id: t.name for t in trows}
    return {
        "items": [
            {
                "id": a.id, "tenant_id": a.tenant_id, "tenant_name": tenants.get(a.tenant_id, ""),
                "upstream_id": a.upstream_id, "name": a.name, "model_id": a.model_id,
                "upstream_version": a.upstream_version, "status": a.status,
                "description": a.description, "created_at": a.created_at.isoformat(),
            }
            for a in rows
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/audit-logs")
async def audit_logs(db: DbSession, action: str = "", page: int = 1, page_size: int = 20):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        stmt = stmt.where(AuditLog.action.like(f"%{action}%"))
    rows, total = await paginate(db, stmt, page, page_size)
    return {
        "items": [
            {
                "id": a.id, "actor_type": a.actor_type, "actor_name": a.actor_name,
                "action": a.action, "target_type": a.target_type, "target_id": a.target_id,
                "detail": a.detail, "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in rows
        ],
        "total": total, "page": page, "page_size": page_size,
    }
