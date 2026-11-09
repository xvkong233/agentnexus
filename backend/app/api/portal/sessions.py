"""客户会话与聊天：创建/列表/事件收发/SSE 流式代理/产物文件。"""
from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession, require_tenant_user
from app.core.errors import bad_request, not_found
from app.models import Agent, Session as SessionRow
from app.services.agentops import create_session_for_tenant, session_view
from app.services.billing import ensure_can_spend
from app.services.bigmodel.factory import get_client_for_tenant

router = APIRouter(dependencies=[Depends(require_tenant_user)])


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
    resources: list | None = None  # [{"type":"file","file_id":...,"mount_path":...}] / memory_store
    vault_ids: list | None = None


@router.get("/sessions")
async def list_sessions(
    request: Request, db: DbSession, status: str = "", source: str = "",
    include_archived: bool = False, keyword: str = "", page: int = 1, page_size: int = 50,
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
    if source:
        stmt = stmt.where(SessionRow.source == source)
    if keyword:
        stmt = stmt.where(SessionRow.title.like(f"%{keyword}%") | SessionRow.upstream_id.like(f"%{keyword}%"))
    from app.api.common import paginate

    rows, total = await paginate(db, stmt, page, page_size)
    items = []
    agent_names = {}
    if rows:
        aids = {r.agent_id for r in rows if r.agent_id}
        if aids:
            arows = (await db.execute(select(Agent).where(Agent.id.in_(aids)))).scalars().all()
            agent_names = {a.id: a.name for a in arows}
    for r in rows:
        v = session_view(r)
        v["agent_name"] = agent_names.get(r.agent_id, "")
        items.append(v)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/sessions")
async def create_session(body: CreateSessionBody, request: Request, db: DbSession):
    from app.models import Tenant

    tenant = await db.get(Tenant, _tenant_id(request))
    row, up = await create_session_for_tenant(
        db, tenant,
        agent_id=body.agent_id,
        environment_id=body.environment_id,
        title=body.title,
        source="web_chat",
        initial_message=body.initial_message,
        file_resources=body.resources,
        vault_ids=body.vault_ids,
    )
    await db.commit()
    return session_view(row, up)


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


class SessionUpdateBody(BaseModel):
    title: str | None = None


@router.post("/sessions/{session_id}")
async def update_session(session_id: str, body: SessionUpdateBody, request: Request, db: DbSession):
    row = await _own_session(db, request, session_id)
    payload: dict = {}
    if body.title is not None:
        payload["title"] = body.title[:256]
        row.title = body.title[:256]
    if payload:
        client = await get_client_for_tenant(db, _tenant_id(request))
        await client.update_session(row.upstream_id, payload)
        await db.commit()
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


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request, db: DbSession):
    row = await _own_session(db, request, session_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    result = await client.delete_session(row.upstream_id)
    await db.delete(row)
    await db.commit()
    return result


class SendEventsBody(BaseModel):
    events: list[dict]


ALLOWED_SEND_TYPES = {"user.message", "user.interrupt", "user.custom_tool_result", "user.tool_confirmation"}


@router.post("/sessions/{session_id}/events")
async def send_events(session_id: str, body: SendEventsBody, request: Request, db: DbSession):
    row = await _own_session(db, request, session_id)
    if not 1 <= len(body.events) <= 10:
        raise bad_request("events 数量须为 1-10")
    has_message = False
    for ev in body.events:
        if ev.get("type") not in ALLOWED_SEND_TYPES:
            raise bad_request(f"不允许发送的事件类型: {ev.get('type')}")
        if ev.get("type") == "user.message":
            has_message = True
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
    limit: int = 100, order: str = "asc", page: str | None = None,
    types: str | None = None,
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
async def stream_events(session_id: str, request: Request, db: DbSession, deltas: bool = True):
    """SSE 实时流代理（live-only）。前端应先连流再发消息。"""
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
            # 上游断开时结束流，前端自动重连补拉历史
            return

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------- 文件 ----------

@router.get("/sessions/{session_id}/files")
async def session_files(session_id: str, request: Request, db: DbSession):
    row = await _own_session(db, request, session_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    return await client.list_files({"scope_id": row.upstream_id, "limit": 100})


@router.post("/files")
async def upload_file(request: Request, db: DbSession, file: UploadFile):
    content = await file.read()
    if len(content) > 500 * 1024 * 1024:
        raise bad_request("单文件上限 500MB")
    client = await get_client_for_tenant(db, _tenant_id(request))
    up = await client.upload_file(file.filename or "upload.bin", content, file.content_type)
    return up


@router.get("/files/{file_id}/content")
async def download_file(file_id: str, request: Request, db: DbSession):
    client = await get_client_for_tenant(db, _tenant_id(request))
    meta = await client.get_file(file_id)
    content = await client.download_file(file_id)
    filename = (meta.get("filename") or "file").replace('"', "")
    return Response(
        content=content,
        media_type=meta.get("mime_type") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
