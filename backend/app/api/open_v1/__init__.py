"""客户开放 API v1：会话/消息/事件(SSE)/用量/钱包/定时任务。

认证：请求头 X-API-Key（门户「API 密钥」创建）。
所有调用实时计量计费，余额不足返回 402。
"""
from fastapi import APIRouter, Depends

from app.api.open_v1 import misc, sessions
from app.core.deps import require_open_api_key

router = APIRouter(prefix="/api/open/v1", dependencies=[Depends(require_open_api_key)])
router.include_router(sessions.router, tags=["open-sessions"])
router.include_router(misc.router, tags=["open-misc"])
