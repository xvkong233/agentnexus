"""Portal / Open API 共享业务逻辑。"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request, not_found
from app.models import Agent, Environment, Session as SessionRow, Tenant, utcnow
from app.services.billing import ensure_can_spend
from app.services.metering import parse_iso

logger = logging.getLogger("app.agentops")

VALID_MODELS = {"glm-5.3", "glm-5.3-flash", "glm-5.3-flashx", "glm-5.3-flashx-legal"}


def build_agent_payload(data: dict) -> dict:
    """从平台请求构建上游 Agent 定义。字段语义与上游一致（省略即不变）。"""
    payload: dict = {}
    if data.get("name") is not None:
        if not (1 <= len(data["name"]) <= 256):
            raise bad_request("name 长度须为 1-256")
        payload["name"] = data["name"]
    model = data.get("model")
    if model:
        if isinstance(model, dict):
            model_id = model.get("id")
            if model_id not in VALID_MODELS:
                raise bad_request(f"model 仅支持: {', '.join(sorted(VALID_MODELS))}")
            m = {"id": model_id}
            if model.get("effort"):
                m["effort"] = model["effort"]
            payload["model"] = m
        else:
            if model not in VALID_MODELS:
                raise bad_request(f"model 仅支持: {', '.join(sorted(VALID_MODELS))}")
            payload["model"] = model
    if "system" in data:
        payload["system"] = data["system"]
    if "description" in data:
        payload["description"] = data["description"]
    if "tools" in data and data["tools"] is not None:
        payload["tools"] = data["tools"]
    if "mcp_servers" in data and data["mcp_servers"] is not None:
        payload["mcp_servers"] = data["mcp_servers"]
    if "skills" in data and data["skills"] is not None:
        payload["skills"] = data["skills"]
    return payload


async def create_session_for_tenant(
    db: AsyncSession,
    tenant: Tenant,
    *,
    agent_id: str,
    environment_id: str,
    title: str = "",
    source: str,
    initial_message: str | None = None,
    file_resources: list | None = None,
    vault_ids: list | None = None,
) -> tuple[SessionRow, dict]:
    """创建上游会话（写入归属 metadata）+ 本地镜像。余额不足抛 402。"""
    agent = await db.get(Agent, agent_id)
    if not agent or agent.tenant_id != tenant.id or agent.status != "active":
        raise not_found("Agent 不存在或不可用")
    env = await db.get(Environment, environment_id)
    if not env or env.tenant_id != tenant.id or env.status != "active":
        raise not_found("运行环境不存在或不可用")

    await ensure_can_spend(db, tenant.id)

    from app.services.bigmodel.factory import get_client_for_tenant

    client = await get_client_for_tenant(db, tenant.id)

    payload: dict = {
        "agent": {"type": "agent", "id": agent.upstream_id, "version": agent.upstream_version},
        "environment_id": env.upstream_id,
        "metadata": {"tenant_id": tenant.id, "source": source, "platform": "agentnexus"},
    }
    if title:
        payload["title"] = title[:256]
    if initial_message:
        payload["initial_events"] = [
            {"type": "user.message", "content": [{"type": "text", "text": initial_message[:20000]}]}
        ]
    if file_resources:
        payload["resources"] = file_resources
    if vault_ids:
        payload["vault_ids"] = vault_ids

    up = await client.create_session(payload)
    row = SessionRow(
        tenant_id=tenant.id,
        upstream_id=up["id"],
        agent_id=agent.id,
        upstream_agent_id=agent.upstream_id,
        upstream_env_id=env.upstream_id,
        title=title or (up.get("title") or ""),
        source=source,
        model_id=agent.model_id,
        status=up.get("status") or "idle",
        upstream_updated_at=parse_iso(up.get("updated_at")),
    )
    db.add(row)
    await db.flush()
    return row, up


def session_view(row: SessionRow, up: dict | None = None) -> dict:
    """本地行 (+可选上游实时数据) → API 视图。"""
    view = {
        "id": row.id,
        "upstream_id": row.upstream_id,
        "tenant_id": row.tenant_id,
        "agent_id": row.agent_id,
        "upstream_agent_id": row.upstream_agent_id,
        "environment_id": row.upstream_env_id,
        "title": row.title,
        "source": row.source,
        "channel_id": row.channel_id,
        "deployment_id": row.deployment_id,
        "model_id": row.model_id,
        "status": row.status,
        "archived": bool(row.archived_at),
        "usage": {
            "input_tokens": row.usage_input,
            "output_tokens": row.usage_output,
            "cache_read_input_tokens": row.usage_cache_read,
            "web_search_requests": row.usage_web_search,
        },
        "cost_total": float(row.cost_total or 0),
        "last_metered_at": row.last_metered_at.isoformat() if row.last_metered_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if up:
        view["upstream"] = up
    return view
