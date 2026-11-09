"""管理端用量统计：仪表盘、计费流水浏览、CSV 导出。"""
import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.common import paginate
from app.core.deps import DbSession, require_admin
from app.models import Session as SessionRow, Tenant, UsageRecord

router = APIRouter(dependencies=[Depends(require_admin)])


def _apply_filters(stmt, tenant_id: str, model_id: str, source: str, start: str, end: str, session_id: str = ""):
    if tenant_id:
        stmt = stmt.where(UsageRecord.tenant_id == tenant_id)
    if session_id:
        stmt = stmt.where(UsageRecord.session_id == session_id)
    if model_id:
        stmt = stmt.where(UsageRecord.model_id == model_id)
    if source:
        stmt = stmt.where(UsageRecord.source == source)
    if start:
        stmt = stmt.where(UsageRecord.created_at >= datetime.fromisoformat(start))
    if end:
        stmt = stmt.where(UsageRecord.created_at <= datetime.fromisoformat(end))
    return stmt


def _record_view(r: UsageRecord, tenant_name: str = "") -> dict:
    return {
        "id": r.id,
        "tenant_id": r.tenant_id,
        "tenant_name": tenant_name,
        "session_id": r.session_id,
        "upstream_session_id": r.upstream_session_id,
        "model_id": r.model_id,
        "source": r.source,
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "cache_read_tokens": r.cache_read_tokens,
        "web_search_requests": r.web_search_requests,
        "cost_input": float(r.cost_input),
        "cost_output": float(r.cost_output),
        "cost_cache": float(r.cost_cache),
        "cost_search": float(r.cost_search),
        "cost_total": float(r.cost_total),
        "price_snapshot": r.price_snapshot,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/dashboard")
async def dashboard(db: DbSession):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_cost = await db.scalar(select(func.coalesce(func.sum(UsageRecord.cost_total), 0)))
    month_cost = await db.scalar(
        select(func.coalesce(func.sum(UsageRecord.cost_total), 0)).where(UsageRecord.created_at >= month_start)
    )
    today_cost = await db.scalar(
        select(func.coalesce(func.sum(UsageRecord.cost_total), 0)).where(UsageRecord.created_at >= today_start)
    )
    month_in = await db.scalar(
        select(func.coalesce(func.sum(UsageRecord.input_tokens), 0)).where(UsageRecord.created_at >= month_start)
    )
    month_out = await db.scalar(
        select(func.coalesce(func.sum(UsageRecord.output_tokens), 0)).where(UsageRecord.created_at >= month_start)
    )
    tenant_count = await db.scalar(select(func.count()).select_from(Tenant))
    running_count = await db.scalar(
        select(func.count()).select_from(SessionRow).where(SessionRow.status == "running")
    )

    # 近 14 天趋势
    series = []
    start14 = today_start - timedelta(days=13)
    rows = (
        await db.execute(
            select(
                func.date(UsageRecord.created_at),
                func.coalesce(func.sum(UsageRecord.cost_total), 0),
                func.coalesce(func.sum(UsageRecord.input_tokens), 0),
                func.coalesce(func.sum(UsageRecord.output_tokens), 0),
            )
            .where(UsageRecord.created_at >= start14)
            .group_by(func.date(UsageRecord.created_at))
        )
    ).all()
    by_date = {str(r[0]): r for r in rows}
    for i in range(14):
        d = (start14 + timedelta(days=i)).date().isoformat()
        r = by_date.get(d)
        series.append({
            "date": d,
            "cost": float(r[1]) if r else 0,
            "input_tokens": int(r[2]) if r else 0,
            "output_tokens": int(r[3]) if r else 0,
        })

    # 模型分布（本月）
    model_rows = (
        await db.execute(
            select(
                UsageRecord.model_id,
                func.coalesce(func.sum(UsageRecord.cost_total), 0),
                func.coalesce(func.sum(UsageRecord.input_tokens), 0),
                func.coalesce(func.sum(UsageRecord.output_tokens), 0),
            )
            .where(UsageRecord.created_at >= month_start)
            .group_by(UsageRecord.model_id)
        )
    ).all()

    return {
        "tenant_count": int(tenant_count or 0),
        "running_sessions": int(running_count or 0),
        "today_cost": float(today_cost or 0),
        "month_cost": float(month_cost or 0),
        "month_input_tokens": int(month_in or 0),
        "month_output_tokens": int(month_out or 0),
        "total_cost": float(total_cost or 0),
        "series": series,
        "model_breakdown": [
            {"model_id": r[0], "cost": float(r[1]), "input_tokens": int(r[2]), "output_tokens": int(r[3])}
            for r in model_rows
        ],
    }


@router.get("/usage-records")
async def usage_records(
    db: DbSession,
    tenant_id: str = "", session_id: str = "", model_id: str = "", source: str = "",
    start: str = "", end: str = "", page: int = 1, page_size: int = 20,
):
    stmt = select(UsageRecord).order_by(UsageRecord.created_at.desc())
    stmt = _apply_filters(stmt, tenant_id, model_id, source, start, end, session_id)
    rows, total = await paginate(db, stmt, page, page_size)
    tenant_names = {}
    if rows:
        tids = {r.tenant_id for r in rows}
        trows = (await db.execute(select(Tenant).where(Tenant.id.in_(tids)))).scalars().all()
        tenant_names = {t.id: t.name for t in trows}
    return {
        "items": [_record_view(r, tenant_names.get(r.tenant_id, "")) for r in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/usage-records/export.csv")
async def export_csv(
    db: DbSession,
    tenant_id: str = "", session_id: str = "", model_id: str = "", source: str = "",
    start: str = "", end: str = "",
):
    stmt = select(UsageRecord).order_by(UsageRecord.created_at.desc()).limit(50000)
    stmt = _apply_filters(stmt, tenant_id, model_id, source, start, end, session_id)
    rows = (await db.execute(stmt)).scalars().all()
    trows = (await db.execute(select(Tenant))).scalars().all()
    tenant_names = {t.id: t.name for t in trows}

    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow(["时间", "租户", "模型", "来源", "输入tokens", "输出tokens", "缓存读tokens",
                     "搜索次数", "输入费用", "输出费用", "缓存费用", "搜索费用", "总费用", "会话ID"])
    for r in rows:
        writer.writerow([
            r.created_at.isoformat() if r.created_at else "", tenant_names.get(r.tenant_id, r.tenant_id),
            r.model_id, r.source, r.input_tokens, r.output_tokens, r.cache_read_tokens,
            r.web_search_requests, float(r.cost_input), float(r.cost_output), float(r.cost_cache),
            float(r.cost_search), float(r.cost_total), r.upstream_session_id,
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=usage_records.csv"},
    )
