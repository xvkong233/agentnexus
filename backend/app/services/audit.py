"""审计日志辅助。"""
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def write_audit(
    db: AsyncSession,
    request: Request | None,
    action: str,
    target_type: str = "",
    target_id: str = "",
    detail: dict | None = None,
) -> None:
    actor_type, actor_id, actor_name = "system", "", "system"
    if request is not None and hasattr(request.state, "actor"):
        actor_type, actor_id, actor_name = request.state.actor
    db.add(
        AuditLog(
            actor_type=actor_type,
            actor_id=actor_id,
            actor_name=actor_name,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail or {},
        )
    )
