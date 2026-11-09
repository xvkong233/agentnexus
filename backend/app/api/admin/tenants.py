"""租户管理：CRUD、钱包充值/调整、门户账号、流水。"""
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.common import paginate
from app.core.deps import DbSession, require_admin
from app.core.errors import bad_request, not_found
from app.core.security import hash_password
from app.models import Tenant, TenantUser, Wallet, WalletTransaction, utcnow
from app.services.audit import write_audit
from app.services.billing import D, q6, wallet_op

router = APIRouter(dependencies=[Depends(require_admin)])


def _tenant_view(db, tenant: Tenant) -> dict:
    return {
        "id": tenant.id,
        "name": tenant.name,
        "code": tenant.code,
        "contact_name": tenant.contact_name,
        "contact_phone": tenant.contact_phone,
        "note": tenant.note,
        "status": tenant.status,
        "low_balance_threshold": float(tenant.low_balance_threshold or 0),
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
    }


class CreateTenantBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=64)
    contact_name: str = ""
    contact_phone: str = ""
    note: str = ""
    low_balance_threshold: float = 0
    # 可选：同时创建门户账号并赠送初始余额
    portal_username: str | None = None
    portal_password: str | None = None
    initial_balance: float = 0


class UpdateTenantBody(BaseModel):
    name: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    note: str | None = None
    status: str | None = None  # active / suspended
    low_balance_threshold: float | None = None


class RechargeBody(BaseModel):
    amount: float = Field(gt=0)
    note: str = ""


class AdjustBody(BaseModel):
    amount: float  # 带符号，负数调减
    note: str = ""


class PortalUserBody(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = ""


class PortalUserUpdateBody(BaseModel):
    password: str | None = Field(default=None, min_length=6, max_length=128)
    status: str | None = None
    display_name: str | None = None


@router.get("/tenants")
async def list_tenants(db: DbSession, keyword: str = "", status: str = "", page: int = 1, page_size: int = 20):
    stmt = select(Tenant).order_by(Tenant.created_at.desc())
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(Tenant.name.like(like) | Tenant.code.like(like))
    if status:
        stmt = stmt.where(Tenant.status == status)
    rows, total = await paginate(db, stmt, page, page_size)
    items = []
    for t in rows:
        view = _tenant_view(db, t)
        wallet = await db.get(Wallet, t.id)
        view["balance"] = float(wallet.balance) if wallet else 0
        view["blocked"] = bool(wallet.blocked) if wallet else False
        items.append(view)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/tenants")
async def create_tenant(body: CreateTenantBody, request: Request, db: DbSession):
    exists = (
        await db.execute(select(Tenant).where(Tenant.code == body.code))
    ).scalar_one_or_none()
    if exists:
        raise bad_request("租户编码已存在")
    tenant = Tenant(
        name=body.name,
        code=body.code,
        contact_name=body.contact_name,
        contact_phone=body.contact_phone,
        note=body.note,
        low_balance_threshold=body.low_balance_threshold,
    )
    db.add(tenant)
    await db.flush()
    db.add(Wallet(tenant_id=tenant.id, balance=0))
    await db.flush()

    if body.portal_username:
        exists_user = (
            await db.execute(select(TenantUser).where(TenantUser.username == body.portal_username))
        ).scalar_one_or_none()
        if exists_user:
            raise bad_request("门户用户名已存在")
        db.add(
            TenantUser(
                tenant_id=tenant.id,
                username=body.portal_username,
                password_hash=hash_password(body.portal_password or "123456"),
                display_name=body.contact_name or body.name,
            )
        )

    if body.initial_balance > 0:
        await wallet_op(
            db, tenant.id, "recharge", q6(D(str(body.initial_balance))),
            operator=request.state.actor[2], note="创建租户赠送", ref_type="tenant", ref_id=tenant.id,
        )
    await write_audit(db, request, "tenant.create", "tenant", tenant.id, {"name": body.name, "code": body.code})
    await db.commit()
    view = _tenant_view(db, tenant)
    wallet = await db.get(Wallet, tenant.id)
    view["balance"] = float(wallet.balance) if wallet else 0
    view["blocked"] = bool(wallet.blocked) if wallet else False
    return view


@router.get("/tenants/{tenant_id}")
async def get_tenant(tenant_id: str, db: DbSession):
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise not_found("租户不存在")
    view = _tenant_view(db, tenant)
    wallet = await db.get(Wallet, tenant.id)
    view["balance"] = float(wallet.balance) if wallet else 0
    view["blocked"] = bool(wallet.blocked) if wallet else False
    view["blocked_reason"] = wallet.blocked_reason if wallet else ""
    users = (
        await db.execute(select(TenantUser).where(TenantUser.tenant_id == tenant.id))
    ).scalars().all()
    view["users"] = [
        {"id": u.id, "username": u.username, "display_name": u.display_name,
         "role": u.role, "status": u.status, "created_at": u.created_at.isoformat()}
        for u in users
    ]
    return view


@router.post("/tenants/{tenant_id}")
async def update_tenant(tenant_id: str, body: UpdateTenantBody, request: Request, db: DbSession):
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise not_found("租户不存在")
    for field in ("name", "contact_name", "contact_phone", "note"):
        if getattr(body, field) is not None:
            setattr(tenant, field, getattr(body, field))
    if body.status is not None:
        if body.status not in ("active", "suspended"):
            raise bad_request("status 仅支持 active/suspended")
        tenant.status = body.status
    if body.low_balance_threshold is not None:
        tenant.low_balance_threshold = body.low_balance_threshold
    await write_audit(db, request, "tenant.update", "tenant", tenant.id, body.model_dump(exclude_none=True))
    await db.commit()
    return _tenant_view(db, tenant)


@router.post("/tenants/{tenant_id}/recharge")
async def recharge(tenant_id: str, body: RechargeBody, request: Request, db: DbSession):
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise not_found("租户不存在")
    wallet = await wallet_op(
        db, tenant_id, "recharge", q6(D(str(body.amount))),
        operator=request.state.actor[2], note=body.note or "管理员充值",
    )
    await write_audit(db, request, "wallet.recharge", "tenant", tenant_id,
                      {"amount": body.amount, "balance": float(wallet.balance)})
    await db.commit()
    return {"balance": float(wallet.balance), "blocked": wallet.blocked}


@router.post("/tenants/{tenant_id}/adjust")
async def adjust(tenant_id: str, body: AdjustBody, request: Request, db: DbSession):
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise not_found("租户不存在")
    amount = q6(D(str(body.amount)))
    if amount == 0:
        raise bad_request("调整金额不能为 0")
    wallet = await wallet_op(
        db, tenant_id, "adjust", amount,
        operator=request.state.actor[2], note=body.note or "管理员调整",
    )
    await write_audit(db, request, "wallet.adjust", "tenant", tenant_id,
                      {"amount": body.amount, "balance": float(wallet.balance)})
    await db.commit()
    return {"balance": float(wallet.balance), "blocked": wallet.blocked}


@router.get("/tenants/{tenant_id}/transactions")
async def transactions(tenant_id: str, db: DbSession, type: str = "", page: int = 1, page_size: int = 20):
    stmt = (
        select(WalletTransaction)
        .where(WalletTransaction.tenant_id == tenant_id)
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
                "operator": t.operator, "ref_type": t.ref_type,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in rows
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.post("/tenants/{tenant_id}/users")
async def create_portal_user(tenant_id: str, body: PortalUserBody, request: Request, db: DbSession):
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise not_found("租户不存在")
    exists = (
        await db.execute(select(TenantUser).where(TenantUser.username == body.username))
    ).scalar_one_or_none()
    if exists:
        raise bad_request("用户名已存在")
    user = TenantUser(
        tenant_id=tenant_id,
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name or body.username,
    )
    db.add(user)
    await write_audit(db, request, "tenant_user.create", "tenant_user", user.id, {"username": body.username})
    await db.commit()
    return {"id": user.id, "username": user.username}


@router.post("/tenants/{tenant_id}/users/{user_id}")
async def update_portal_user(
    tenant_id: str, user_id: str, body: PortalUserUpdateBody, request: Request, db: DbSession
):
    user = await db.get(TenantUser, user_id)
    if not user or user.tenant_id != tenant_id:
        raise not_found("门户用户不存在")
    if body.password:
        user.password_hash = hash_password(body.password)
    if body.status in ("active", "disabled"):
        user.status = body.status
    if body.display_name is not None:
        user.display_name = body.display_name
    await write_audit(db, request, "tenant_user.update", "tenant_user", user.id,
                      body.model_dump(exclude_none=True))
    await db.commit()
    return {"id": user.id, "username": user.username, "status": user.status}
