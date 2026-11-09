"""客户运行环境管理：CRUD（镜像上游）。"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession, require_tenant_user
from app.core.errors import bad_request, not_found
from app.models import Environment
from app.services.bigmodel.factory import get_client_for_tenant

router = APIRouter(dependencies=[Depends(require_tenant_user)])

VALID_PKG_KEYS = {"apt", "cargo", "gem", "go", "npm", "pip"}


class EnvBody(BaseModel):
    name: str | None = None
    packages: dict | None = None       # {"pip": ["pandas"], ...}
    networking: dict | None = None     # {"type":"unrestricted"} | {"type":"limited", ...}
    apt: list[str] | None = None       # 便捷字段，等价 packages.apt
    pip: list[str] | None = None
    npm: list[str] | None = None


def build_env_config(body: EnvBody) -> dict:
    packages: dict = {}
    for k, v in (body.packages or {}).items():
        if k not in VALID_PKG_KEYS:
            raise bad_request(f"不支持的包管理器: {k}（仅支持 {', '.join(sorted(VALID_PKG_KEYS))}）")
        packages[k] = list(v or [])
    for key in ("apt", "pip", "npm"):
        val = getattr(body, key)
        if val:
            packages[key] = list(val)
    networking = body.networking or {"type": "unrestricted"}
    if networking.get("type") not in ("unrestricted", "limited"):
        raise bad_request("networking.type 仅支持 unrestricted / limited")
    config: dict = {"type": "cloud", "packages": packages, "networking": networking}
    if not packages and networking.get("type") == "unrestricted":
        # 与上游一致：空 packages 时省略键
        config["packages"] = {}
    return config


def _view(e: Environment) -> dict:
    return {
        "id": e.id,
        "upstream_id": e.upstream_id,
        "name": e.name,
        "config": e.config,
        "status": e.status,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


@router.get("/environments")
async def list_envs(request: Request, db: DbSession):
    rows = (
        await db.execute(
            select(Environment)
            .where(Environment.tenant_id == request.state.tenant_id)
            .order_by(Environment.created_at.desc())
        )
    ).scalars().all()
    return {"items": [_view(e) for e in rows]}


@router.post("/environments")
async def create_env(body: EnvBody, request: Request, db: DbSession):
    if not body.name:
        raise bad_request("name 必填")
    config = build_env_config(body)
    client = await get_client_for_tenant(db, request.state.tenant_id)
    up = await client.create_environment({"name": body.name, "config": config})
    row = Environment(
        tenant_id=request.state.tenant_id,
        upstream_id=up["id"],
        name=up.get("name") or body.name,
        config=up.get("config") or config,
    )
    db.add(row)
    await db.commit()
    return _view(row)


@router.post("/environments/{env_id}")
async def update_env(env_id: str, body: EnvBody, request: Request, db: DbSession):
    row = await db.get(Environment, env_id)
    if not row or row.tenant_id != request.state.tenant_id:
        raise not_found("环境不存在")
    payload: dict = {}
    if body.name:
        payload["name"] = body.name
    if body.packages is not None or body.apt is not None or body.pip is not None or body.npm is not None:
        payload["config"] = build_env_config(body)
    elif body.networking is not None:
        cfg = dict(row.config or {})
        cfg["networking"] = body.networking
        payload["config"] = cfg
    client = await get_client_for_tenant(db, request.state.tenant_id)
    up = await client.update_environment(row.upstream_id, payload)
    row.name = up.get("name") or row.name
    row.config = up.get("config") or row.config
    await db.commit()
    return _view(row)


@router.post("/environments/{env_id}/archive")
async def archive_env(env_id: str, request: Request, db: DbSession):
    row = await db.get(Environment, env_id)
    if not row or row.tenant_id != request.state.tenant_id:
        raise not_found("环境不存在")
    client = await get_client_for_tenant(db, request.state.tenant_id)
    await client.archive_environment(row.upstream_id)
    row.status = "archived"
    await db.commit()
    return {"ok": True}
