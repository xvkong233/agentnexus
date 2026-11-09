"""通用列表分页工具。"""
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def paginate(db: AsyncSession, stmt: Select, page: int = 1, page_size: int = 20) -> tuple[list, int]:
    page = max(1, int(page))
    page_size = min(200, max(1, int(page_size)))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    return list(rows), int(total)
