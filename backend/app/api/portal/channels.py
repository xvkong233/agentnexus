"""客户聊天渠道管理：飞书 / 企业微信 / 钉钉 / 个人微信（全官方支持渠道）。

渠道 API 走上游独立基址 forward/v0；凭据由上游托管，平台不落库。
个人微信创建后需扫码绑定：创建成功自动申请二维码，前端轮询绑定状态。
"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession, require_tenant_user
from app.core.errors import bad_request, not_found
from app.models import Agent, Channel, Environment
from app.services.bigmodel.factory import get_client_for_tenant

router = APIRouter(dependencies=[Depends(require_tenant_user)])

CHANNEL_TYPES = ("feishu", "wecom", "dingtalk", "wechat")


def _tenant_id(request) -> str:
    return request.state.tenant_id


async def _own(db, request, channel_id: str) -> Channel:
    row = await db.get(Channel, channel_id)
    if not row or row.tenant_id != _tenant_id(request):
        raise not_found("渠道不存在")
    return row


def _view(c: Channel) -> dict:
    return {
        "id": c.id,
        "upstream_id": c.upstream_id,
        "channel_type": c.channel_type,
        "name": c.name,
        "template": c.template,
        "binding_status": c.binding_status,
        "connection_status": c.connection_status,
        "last_error": c.last_error,
        "status": c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


class ChannelBody(BaseModel):
    channel_type: str
    name: str
    agent_id: str
    environment_id: str
    credentials: dict | None = None   # feishu{app_id,app_secret} wecom{bot_id,secret} dingtalk{client_id,client_secret} wechat 不传
    extra_config: dict | None = None  # 卡片模板等附加 channel_config


@router.get("/channels")
async def list_channels(request: Request, db: DbSession):
    rows = (
        await db.execute(
            select(Channel)
            .where(Channel.tenant_id == _tenant_id(request), Channel.status == "active")
            .order_by(Channel.created_at.desc())
        )
    ).scalars().all()
    return {"items": [_view(c) for c in rows]}


@router.post("/channels")
async def create_channel(body: ChannelBody, request: Request, db: DbSession):
    if body.channel_type not in CHANNEL_TYPES:
        raise bad_request(f"channel_type 仅支持: {', '.join(CHANNEL_TYPES)}")
    agent = await db.get(Agent, body.agent_id)
    if not agent or agent.tenant_id != _tenant_id(request) or agent.status != "active":
        raise not_found("Agent 不存在或不可用")
    env = await db.get(Environment, body.environment_id)
    if not env or env.tenant_id != _tenant_id(request) or env.status != "active":
        raise not_found("运行环境不存在或不可用")

    template = {
        "agent": {"type": "agent", "id": agent.upstream_id, "version": agent.upstream_version},
        "environment_id": env.upstream_id,
    }
    channel_config: dict = {}
    if body.channel_type == "wechat":
        if body.credentials:
            raise bad_request("个人微信渠道不传凭据，创建后扫码绑定")
    else:
        if not body.credentials:
            raise bad_request("该渠道需要 credentials 凭据")
        channel_config["credentials"] = body.credentials
    if body.extra_config:
        channel_config.update(body.extra_config)

    client = await get_client_for_tenant(db, _tenant_id(request))
    payload = {
        "channel_type": body.channel_type,
        "name": body.name[:256],
        "template": template,
        "channel_config": channel_config,
    }
    up = await client.create_channel(payload)
    row = Channel(
        tenant_id=_tenant_id(request),
        upstream_id=up["id"],
        channel_type=body.channel_type,
        name=up.get("name") or body.name,
        template=up.get("template") or template,
        binding_status=up.get("binding_status") or "",
        connection_status=up.get("connection_status") or "",
        last_error=up.get("last_error") or "",
    )
    db.add(row)
    await db.flush()

    qr = None
    if body.channel_type == "wechat":
        try:
            qr = await client.create_wechat_qr_session(row.upstream_id)
        except Exception:
            qr = None

    await db.commit()
    view = _view(row)
    view["qr"] = qr
    return view


@router.get("/channels/{channel_id}")
async def get_channel(channel_id: str, request: Request, db: DbSession):
    row = await _own(db, request, channel_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    try:
        up = await client.get_channel(row.upstream_id)
        row.binding_status = up.get("binding_status") or row.binding_status
        row.connection_status = up.get("connection_status") or row.connection_status
        row.last_error = up.get("last_error") or ""
        row.name = up.get("name") or row.name
        await db.commit()
    except Exception:
        pass
    return _view(row)


class ChannelPatchBody(BaseModel):
    channel_config: dict | None = None  # 仅卡片模板等可更新项（凭据/Agent 不可改）


@router.patch("/channels/{channel_id}")
async def patch_channel(channel_id: str, body: ChannelPatchBody, request: Request, db: DbSession):
    row = await _own(db, request, channel_id)
    if not body.channel_config:
        raise bad_request("channel_config 必填（注意：上游不允许修改凭据与 Agent 模板）")
    if "credentials" in body.channel_config:
        raise bad_request("凭据创建后不可修改，如需更换请删除渠道重建")
    client = await get_client_for_tenant(db, _tenant_id(request))
    await client.patch_channel(row.upstream_id, {"channel_config": body.channel_config})
    await db.commit()
    return {"ok": True}


@router.delete("/channels/{channel_id}")
async def delete_channel(channel_id: str, request: Request, db: DbSession):
    row = await _own(db, request, channel_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    await client.delete_channel(row.upstream_id)
    row.status = "deleted"
    await db.commit()
    return {"ok": True}


@router.post("/channels/{channel_id}/qr-session")
async def new_qr_session(channel_id: str, request: Request, db: DbSession):
    """个人微信（重新）申请扫码绑定二维码。"""
    row = await _own(db, request, channel_id)
    if row.channel_type != "wechat":
        raise bad_request("仅个人微信渠道需要扫码绑定")
    client = await get_client_for_tenant(db, _tenant_id(request))
    return await client.create_wechat_qr_session(row.upstream_id)


@router.get("/channels/{channel_id}/qr-session/{session_key}")
async def qr_status(channel_id: str, session_key: str, request: Request, db: DbSession):
    row = await _own(db, request, channel_id)
    client = await get_client_for_tenant(db, _tenant_id(request))
    return await client.get_wechat_qr_session(row.upstream_id, session_key)
