"""管理端路由聚合，前缀 /api/admin。"""
from fastapi import APIRouter

from app.api.admin import auth, platform_keys, pricing, tenants, usage, views

router = APIRouter(prefix="/api/admin")
router.include_router(auth.router, tags=["admin-auth"])
router.include_router(tenants.router, tags=["admin-tenants"])
router.include_router(pricing.router, tags=["admin-pricing"])
router.include_router(platform_keys.router, tags=["admin-platform-keys"])
router.include_router(usage.router, tags=["admin-usage"])
router.include_router(views.router, tags=["admin-views"])
