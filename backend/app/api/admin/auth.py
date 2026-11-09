"""管理员认证。"""
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession
from app.core.errors import PlatformError
from app.core.security import create_token, verify_password
from app.models import Admin

router = APIRouter()


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
async def login(body: LoginBody, db: DbSession):
    admin = (
        await db.execute(select(Admin).where(Admin.username == body.username))
    ).scalar_one_or_none()
    if not admin or not verify_password(body.password, admin.password_hash):
        raise PlatformError(401, "invalid_credentials", "用户名或密码错误")
    token = create_token("admin", admin.id, name=admin.username)
    return {"token": token, "admin": {"id": admin.id, "username": admin.username, "display_name": admin.display_name}}
