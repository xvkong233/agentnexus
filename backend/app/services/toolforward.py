"""自定义工具回调转发：requires_action 事件 → 租户 Webhook → 自动回传结果。"""
import json
import logging
import time

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hmac_sign
from app.models import Agent, Session as SessionRow, ToolWebhook
from app.services.bigmodel.factory import get_client_for_tenant

logger = logging.getLogger("app.toolforward")

MAX_EVENTS_PER_PASS = 5


async def forward_pending_for_session(db: AsyncSession, row: SessionRow) -> int:
    """检查会话中未解决的 agent.custom_tool_use，转发到租户 Webhook 并回传结果。"""
    if not row.agent_id:
        return 0
    agent = await db.get(Agent, row.agent_id)
    if not agent:
        return 0
    tools = agent.tools or []
    if not any(isinstance(t, dict) and t.get("type") == "custom" for t in tools):
        return 0
    hook = (
        await db.execute(select(ToolWebhook).where(ToolWebhook.tenant_id == row.tenant_id))
    ).scalar_one_or_none()
    if not hook or not hook.url or hook.status != "active":
        return 0

    client = await get_client_for_tenant(db, row.tenant_id)
    resp = await client.list_events(
        row.upstream_id, {"types": "agent.custom_tool_use,user.custom_tool_result", "order": "desc", "limit": 50}
    )
    data = resp.get("data") or []
    resolved = {
        e.get("custom_tool_use_id") for e in data if e.get("type") == "user.custom_tool_result"
    }
    pending = [
        e for e in data if e.get("type") == "agent.custom_tool_use" and e.get("id") not in resolved
    ][:MAX_EVENTS_PER_PASS]

    forwarded = 0
    for ev in pending:
        payload = json.dumps(
            {
                "session_id": row.id,
                "upstream_session_id": row.upstream_id,
                "tool_use_id": ev.get("id"),
                "name": ev.get("name"),
                "input": ev.get("input"),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        ts = str(int(time.time()))
        headers = {
            "Content-Type": "application/json",
            "X-Timestamp": ts,
            "X-Signature": hmac_sign(hook.secret, payload, ts),
        }
        content_blocks: list = []
        is_error = False
        try:
            async with httpx.AsyncClient(timeout=30) as http:
                r = await http.post(hook.url, content=payload, headers=headers)
            if r.status_code >= 400:
                is_error = True
                content_blocks = [{"type": "text", "text": f"webhook http {r.status_code}"}]
            else:
                try:
                    out = r.json()
                    is_error = bool(out.get("is_error", False))
                    content_blocks = out.get("content") or [{"type": "text", "text": r.text[:4000]}]
                except Exception:
                    content_blocks = [{"type": "text", "text": r.text[:4000]}]
        except Exception as exc:
            is_error = True
            content_blocks = [{"type": "text", "text": f"webhook 调用失败: {exc}"}]

        await client.send_events(
            row.upstream_id,
            [
                {
                    "type": "user.custom_tool_result",
                    "custom_tool_use_id": ev.get("id"),
                    "content": content_blocks,
                    "is_error": is_error,
                }
            ],
        )
        forwarded += 1
        logger.info("会话 %s 自定义工具 %s 已转发并回传", row.upstream_id, ev.get("name"))
    return forwarded


async def delayed_forward(session_id: str, delay_seconds: float = 3.0, attempts: int = 3) -> None:
    """发送消息后的延迟转发（独立 DB 会话的后台任务）。"""
    import asyncio

    from app.db import SessionLocal

    await asyncio.sleep(delay_seconds)
    for i in range(attempts):
        try:
            async with SessionLocal() as db:
                row = await db.get(SessionRow, session_id)
                if not row:
                    return
                count = await forward_pending_for_session(db, row)
                await db.commit()
                if count:
                    return
        except Exception:
            logger.exception("延迟转发失败 session=%s", session_id)
        await asyncio.sleep(2.5)
