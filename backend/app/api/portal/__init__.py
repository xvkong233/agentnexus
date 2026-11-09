"""客户门户路由聚合，前缀 /api/portal。"""
from fastapi import APIRouter

from app.api.portal import (
    agents,
    apikeys,
    auth,
    channels,
    dashboard,
    deployments,
    environments,
    sessions,
    toolwebhook,
    vaults,
    wallet,
)

router = APIRouter(prefix="/api/portal")
router.include_router(auth.router, tags=["portal-auth"])
router.include_router(dashboard.router, tags=["portal-dashboard"])
router.include_router(agents.router, tags=["portal-agents"])
router.include_router(environments.router, tags=["portal-environments"])
router.include_router(sessions.router, tags=["portal-sessions"])
router.include_router(deployments.router, tags=["portal-deployments"])
router.include_router(channels.router, tags=["portal-channels"])
router.include_router(vaults.router, tags=["portal-vaults"])
router.include_router(wallet.router, tags=["portal-wallet"])
router.include_router(apikeys.router, tags=["portal-apikeys"])
router.include_router(toolwebhook.router, tags=["portal-toolwebhook"])
