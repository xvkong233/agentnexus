"""客户门户工作台。"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from app.core.deps import DbSession, require_tenant_user
from app.models import Agent, Session as SessionRow, UsageRecord, Wallet

router = APIRouter(dependencies=[Depends(require_tenant_user)])


@router.get("/dashboard")
async def dashboard(request: Request, db: DbSession):
    tid = request.state.tenant_id
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    wallet = await db.get(Wallet, tid)
    month_cost = await db.scalar(
        select(func.coalesce(func.sum(UsageRecord.cost_total), 0))
        .where(UsageRecord.tenant_id == tid, UsageRecord.created_at >= month_start)
    )
    month_in = await db.scalar(
        select(func.coalesce(func.sum(UsageRecord.input_tokens), 0))
        .where(UsageRecord.tenant_id == tid, UsageRecord.created_at >= month_start)
    )
    month_out = await db.scalar(
        select(func.coalesce(func.sum(UsageRecord.output_tokens), 0))
        .where(UsageRecord.tenant_id == tid, UsageRecord.created_at >= month_start)
    )
    agent_count = await db.scalar(
        select(func.count()).select_from(Agent).where(Agent.tenant_id == tid, Agent.status == "active")
    )
    running = await db.scalar(
        select(func.count()).select_from(SessionRow)
        .where(SessionRow.tenant_id == tid, SessionRow.status == "running", SessionRow.archived_at.is_(None))
    )

    series = []
    start14 = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=13)
    rows = (
        await db.execute(
            select(
                func.date(UsageRecord.created_at),
                func.coalesce(func.sum(UsageRecord.cost_total), 0),
                func.coalesce(func.sum(UsageRecord.input_tokens + UsageRecord.output_tokens), 0),
            )
            .where(UsageRecord.tenant_id == tid, UsageRecord.created_at >= start14)
            .group_by(func.date(UsageRecord.created_at))
        )
    ).all()
    by_date = {str(r[0]): r for r in rows}
    for i in range(14):
        d = (start14 + timedelta(days=i)).date().isoformat()
        r = by_date.get(d)
        series.append({"date": d, "cost": float(r[1]) if r else 0, "tokens": int(r[2]) if r else 0})

    recent = (
        await db.execute(
            select(SessionRow)
            .where(SessionRow.tenant_id == tid, SessionRow.archived_at.is_(None))
            .order_by(SessionRow.created_at.desc())
            .limit(8)
        )
    ).scalars().all()

    return {
        "wallet": {
            "balance": float(wallet.balance) if wallet else 0,
            "blocked": bool(wallet.blocked) if wallet else False,
            "blocked_reason": wallet.blocked_reason if wallet else "",
        },
        "month_cost": float(month_cost or 0),
        "month_input_tokens": int(month_in or 0),
        "month_output_tokens": int(month_out or 0),
        "agent_count": int(agent_count or 0),
        "running_sessions": int(running or 0),
        "series": series,
        "recent_sessions": [
            {
                "id": s.id, "title": s.title or "(未命名)", "status": s.status,
                "source": s.source, "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in recent
        ],
    }
