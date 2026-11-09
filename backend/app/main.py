"""应用入口：lifespan（建表+种子+调度器）、异常处理、路由挂载。"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.errors import PlatformError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.seed import init_db
    from app.workers.scheduler import start_scheduler, stop_scheduler

    await init_db()
    logger.info("数据库初始化完成 (mock=%s)", settings.bigmodel_mock)
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(PlatformError)
async def platform_error_handler(request: Request, exc: PlatformError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "detail": exc.detail},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("未处理异常: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"code": "internal_error", "message": str(exc) or "服务器内部错误"},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok", "mock": settings.bigmodel_mock}


# 路由
from app.api.admin import router as admin_router  # noqa: E402
from app.api.open_v1 import router as open_router  # noqa: E402
from app.api.portal import router as portal_router  # noqa: E402

app.include_router(admin_router)
app.include_router(portal_router)
app.include_router(open_router)
