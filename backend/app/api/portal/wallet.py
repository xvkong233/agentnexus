"""客户钱包 / 计费流水 / 月度账单。"""
import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.common import paginate
from app.core.deps import DbSession, require_tenant_user
from app.models import UsageRecord, Wallet, WalletTransaction

router = APIRouter(dependencies=[Depends(require_tenant_user)])


def _tenant_id(request) -> str:
    return request.state.tenant_id


@router.get("/wallet")
async def wallet(request: Request, db: DbSession):
    w = await db.get(Wallet, _tenant_id(request))
    return {
        "balance": float(w.balance) if w else 0,
        "blocked": bool(w.blocked) if w else False,
        "blocked_reason": w.blocked_reason if w else "",
    }


@router.get("/wallet/transactions")
async def transactions(request: Request, db: DbSession, type: str = "", page: int = 1, page_size: int = 20):
    stmt = (
        select(WalletTransaction)
        .where(WalletTransaction.tenant_id == _tenant_id(request))
        .order_by(WalletTransaction.created_at.desc())
    )
    if type:
        stmt = stmt.where(WalletTransaction.type == type)
    rows, total = await paginate(db, stmt, page, page_size)
    return {
        "items": [
            {
                "id": t.id, "type": t.type, "amount": float(t.amount),
                "balance_after": float(t.balance_after), "note": t.note,
                "operator": t.operator, "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in rows
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/usage-records")
async def usage_records(
    request: Request, db: DbSession, model_id: str = "", source: str = "",
    start: str = "", end: str = "", page: int = 1, page_size: int = 20,
):
    stmt = (
        select(UsageRecord)
        .where(UsageRecord.tenant_id == _tenant_id(request))
        .order_by(UsageRecord.created_at.desc())
    )
    if model_id:
        stmt = stmt.where(UsageRecord.model_id == model_id)
    if source:
        stmt = stmt.where(UsageRecord.source == source)
    if start:
        stmt = stmt.where(UsageRecord.created_at >= datetime.fromisoformat(start))
    if end:
        stmt = stmt.where(UsageRecord.created_at <= datetime.fromisoformat(end))
    rows, total = await paginate(db, stmt, page, page_size)
    return {
        "items": [
            {
                "id": r.id, "session_id": r.session_id, "model_id": r.model_id, "source": r.source,
                "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
                "cache_read_tokens": r.cache_read_tokens, "web_search_requests": r.web_search_requests,
                "cost_input": float(r.cost_input), "cost_output": float(r.cost_output),
                "cost_cache": float(r.cost_cache), "cost_search": float(r.cost_search),
                "cost_total": float(r.cost_total), "price_snapshot": r.price_snapshot,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/usage/summary")
async def usage_summary(request: Request, db: DbSession, month: str = ""):
    """月度账单：按日汇总 + 按模型汇总。month=YYYY-MM，默认当月（UTC）。"""
    tid = _tenant_id(request)
    now = datetime.now(timezone.utc)
    if month and len(month) >= 7:
        year, m = int(month[:4]), int(month[5:7])
    else:
        year, m = now.year, now.month
    start = datetime(year, m, 1, tzinfo=timezone.utc)
    nxt_year, nxt_m = (year + 1, 1) if m == 12 else (year, m + 1)
    end = datetime(nxt_year, nxt_m, 1, tzinfo=timezone.utc)
    cond = (UsageRecord.tenant_id == tid, UsageRecord.created_at >= start, UsageRecord.created_at < end)

    day_rows = (
        await db.execute(
            select(
                func.date(UsageRecord.created_at),
                func.coalesce(func.sum(UsageRecord.cost_total), 0),
                func.coalesce(func.sum(UsageRecord.input_tokens), 0),
                func.coalesce(func.sum(UsageRecord.output_tokens), 0),
                func.coalesce(func.sum(UsageRecord.cache_read_tokens), 0),
            )
            .where(*cond)
            .group_by(func.date(UsageRecord.created_at))
            .order_by(func.date(UsageRecord.created_at))
        )
    ).all()
    model_rows = (
        await db.execute(
            select(
                UsageRecord.model_id,
                func.coalesce(func.sum(UsageRecord.cost_total), 0),
                func.coalesce(func.sum(UsageRecord.input_tokens), 0),
                func.coalesce(func.sum(UsageRecord.output_tokens), 0),
                func.count(),
            )
            .where(*cond)
            .group_by(UsageRecord.model_id)
        )
    ).all()
    total_row = (
        await db.execute(
            select(
                func.coalesce(func.sum(UsageRecord.cost_total), 0),
                func.coalesce(func.sum(UsageRecord.input_tokens), 0),
                func.coalesce(func.sum(UsageRecord.output_tokens), 0),
                func.coalesce(func.sum(UsageRecord.cache_read_tokens), 0),
                func.coalesce(func.sum(UsageRecord.web_search_requests), 0),
            ).where(*cond)
        )
    ).one()

    return {
        "month": f"{year:04d}-{m:02d}",
        "total": {
            "cost": float(total_row[0]), "input_tokens": int(total_row[1]),
            "output_tokens": int(total_row[2]), "cache_read_tokens": int(total_row[3]),
            "web_search_requests": int(total_row[4]),
        },
        "by_day": [
            {"date": str(r[0]), "cost": float(r[1]), "input_tokens": int(r[2]),
             "output_tokens": int(r[3]), "cache_read_tokens": int(r[4])}
            for r in day_rows
        ],
        "by_model": [
            {"model_id": r[0], "cost": float(r[1]), "input_tokens": int(r[2]),
             "output_tokens": int(r[3]), "records": int(r[4])}
            for r in model_rows
        ],
    }


@router.get("/usage-records/export.csv")
async def export_csv(request: Request, db: DbSession, start: str = "", end: str = ""):
    stmt = (
        select(UsageRecord)
        .where(UsageRecord.tenant_id == _tenant_id(request))
        .order_by(UsageRecord.created_at.desc())
        .limit(50000)
    )
    if start:
        stmt = stmt.where(UsageRecord.created_at >= datetime.fromisoformat(start))
    if end:
        stmt = stmt.where(UsageRecord.created_at <= datetime.fromisoformat(end))
    rows = (await db.execute(stmt)).scalars().all()

    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow(["时间", "模型", "来源", "输入tokens", "输出tokens", "缓存读tokens", "搜索次数",
                     "输入费用", "输出费用", "缓存费用", "搜索费用", "总费用", "会话ID"])
    for r in rows:
        writer.writerow([
            r.created_at.isoformat() if r.created_at else "", r.model_id, r.source,
            r.input_tokens, r.output_tokens, r.cache_read_tokens, r.web_search_requests,
            float(r.cost_input), float(r.cost_output), float(r.cost_cache),
            float(r.cost_search), float(r.cost_total), r.upstream_session_id,
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=usage.csv"},
    )
