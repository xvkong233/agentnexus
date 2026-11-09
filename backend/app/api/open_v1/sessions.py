"""Open API：会话生命周期 + 消息 + 事件（含 SSE）+ 产物文件。"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession, require_open_api_key
from app.core.errors import bad_request, not_found
from app.models import TenantApiKey, Session as SessionRow, Tenant
from app.services.agentops import create_session_for_tenant, session_view
from app.services.billing import ensure_can_spend
from app.services.bigmodel.factory import get_client_for_tenant

router = APIRouter()


def _tenant_id(request) -> str:
    return request.state.tenant_id


async def _own_session(db, request, session_id: str) -> SessionRow:
    row = await db.get(SessionRow, session_id)
    if not row or row.tenant_id != _tenant_id(request):
        raise not_found("会话不存在")
    return row


class CreateSessionBody(BaseModel):
    agent_id: str
    environment_id: str
    title: str = ""
    initial_message: str | None = None
    resources: list | None = None
    vault_ids: list | None = None


@router.post("/sessions")
async def create_session(body: CreateSessionBody, request: Request, db: DbSession):
    tenant = await db.get(Tenant, _tenant_id(request))
    row, up = await create_session_for_tenant(
        db, tenant,
        agent_id=body.agent_id,
        environment_id=body.environment_id,
        title=body.title,
        source="open_api",
        initial_message=body.initial_message,
        file_resources=body.resources,
        vault_ids=body.vault_ids,
    )
    await db.commit()
    return session_view(row, up)


@router.get("/sessions")
async def list_sessions(
    request: Request, db: DbSession, status: str = "", include_archived: bool = False,
    page: int = 1, page_size: int = 20,
):
    stmt = (
        select(SessionRow)
        .where(SessionRow.tenant_id == _tenant_id(request))
        .order_by(SessionRow.created_at.desc())
    )
    if not include_archived:
        stmt = stmt.where(SessionRow.archived_at.is_(None))
    if status:
        stmt = stmt.where(SessionRow.status == status)
    from app.api.common import paginate

    rows, total = await paginate(db, stmt, page, page_size)
    return {"items": [session_view(r) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request, db: DbSession):
    row = await _own_session(db, request, session_id)
    up = None
    try:
        client = await get_client_for_tenant(db, _tenant_id(request))
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


@router.post("/sessions/{session_id}/archive")
async def archive_session(session_id: str, request: Request, db: DbSession):
    row = await _own_session(db, request, session_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    await client.archive_session(row.upstream_id)
    from app.models import utcnow

    row.archived_at = utcnow()
    await db.commit()
    return {"ok": True}


class MessageBody(BaseModel):
    text: str


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, body: MessageBody, request: Request, db: DbSession):
    """便捷接口：发送一条文本消息。"""
    row = await _own_session(db, request, session_id)
    if not body.text.strip():
        raise bad_request("text 不能为空")
    await ensure_can_spend(db, _tenant_id(request))
    client = await get_client_for_tenant(db, _tenant_id(request))
    result = await client.send_events(
        row.upstream_id, [{"type": "user.message", "content": [{"type": "text", "text": body.text}]}]
    )
    row.status = "running"
    await db.commit()
    return result


class SendEventsBody(BaseModel):
    events: list[dict]


ALLOWED = {"user.message", "user.interrupt", "user.custom_tool_result", "user.tool_confirmation"}


@router.post("/sessions/{session_id}/events")
async def send_events(session_id: str, body: SendEventsBody, request: Request, db: DbSession):
    row = await _own_session(db, request, session_id)
    if not 1 <= len(body.events) <= 10:
        raise bad_request("events 数量须为 1-10")
    has_message = any(e.get("type") == "user.message" for e in body.events)
    for ev in body.events:
        if ev.get("type") not in ALLOWED:
            raise bad_request(f"不允许发送的事件类型: {ev.get('type')}")
    if has_message:
        await ensure_can_spend(db, _tenant_id(request))
    client = await get_client_for_tenant(db, _tenant_id(request))
    result = await client.send_events(row.upstream_id, body.events)
    if has_message:
        row.status = "running"
    await db.commit()
    return result


@router.get("/sessions/{session_id}/events")
async def list_events(
    session_id: str, request: Request, db: DbSession,
    limit: int = 100, order: str = "asc", page: str | None = None, types: str | None = None,
):
    row = await _own_session(db, request, session_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    params: dict = {"limit": min(500, max(1, limit)), "order": order}
    if page:
        params["page"] = page
    if types:
        params["types"] = types
    return await client.list_events(row.upstream_id, params)


@router.get("/sessions/{session_id}/events/stream")
async def stream_events(session_id: str, request: Request, db: DbSession, deltas: bool = False):
    """SSE 事件流。建议携带 Authorization: Bearer <API Key> 或 X-API-Key。"""
    row = await _own_session(db, request, session_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    params: dict = {}
    if deltas:
        params["event_deltas[]"] = ["agent.message", "agent.thinking"]

    async def gen():
        try:
            async for chunk in client.stream_events(row.upstream_id, params):
                yield chunk
        except Exception:
            return

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions/{session_id}/files")
async def session_files(session_id: str, request: Request, db: DbSession):
    row = await _own_session(db, request, session_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    return await client.list_files({"scope_id": row.upstream_id, "limit": 100})


@router.get("/files/{file_id}/content")
async def download_file(file_id: str, request: Request, db: DbSession):
    from fastapi.responses import Response

    client = await get_client_for_tenant(db, _tenant_id(request))
    meta = await client.get_file(file_id)
    content = await client.download_file(file_id)
    filename = (meta.get("filename") or "file").replace('"', "")
    return Response(
        content=content, media_type=meta.get("mime_type") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
