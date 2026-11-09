"""租户自定义工具回调配置。

Agent 配置了 custom 类型工具时，会话会停在 requires_action；平台把
agent.custom_tool_use 以 HMAC-SHA256 签名转发到此 URL，拿到响应后自动回传
user.custom_tool_result，使无人值守场景（渠道/定时任务）也能用自定义工具。
"""
import secrets

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession, require_tenant_user
from app.models import ToolWebhook

router = APIRouter(dependencies=[Depends(require_tenant_user)])


class WebhookBody(BaseModel):
    url: str = ""  # 空字符串 = 停用


async def _get_hook(db, tenant_id: str) -> ToolWebhook | None:
    return (
        await db.execute(select(ToolWebhook).where(ToolWebhook.tenant_id == tenant_id))
    ).scalar_one_or_none()


@router.get("/tool-webhook")
async def get_webhook(request: Request, db: DbSession):
    hook = await _get_hook(db, request.state.tenant_id)
    if not hook:
        return {"url": "", "secret": "", "status": "inactive"}
    return {"url": hook.url, "secret": hook.secret, "status": hook.status}


@router.put("/tool-webhook")
async def put_webhook(body: WebhookBody, request: Request, db: DbSession):
    hook = await _get_hook(db, request.state.tenant_id)
    if not hook:
        hook = ToolWebhook(tenant_id=request.state.tenant_id, url=body.url.strip(), secret=secrets.token_urlsafe(24))
        db.add(hook)
    else:
        hook.url = body.url.strip()
        hook.status = "active" if hook.url else "inactive"
    await db.commit()
    return {"url": hook.url, "secret": hook.secret, "status": hook.status}


@router.post("/tool-webhook/rotate-secret")
async def rotate_secret(request: Request, db: DbSession):
    hook = await _get_hook(db, request.state.tenant_id)
    if not hook:
        hook = ToolWebhook(tenant_id=request.state.tenant_id, url="", secret=secrets.token_urlsafe(24))
        db.add(hook)
    else:
        hook.secret = secrets.token_urlsafe(24)
    await db.commit()
    return {"url": hook.url, "secret": hook.secret, "status": hook.status}
