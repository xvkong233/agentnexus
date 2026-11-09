"""内嵌 APScheduler：计量 / 同步 / 守护三个周期任务。单实例部署。"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings

logger = logging.getLogger("app.scheduler")
_scheduler: AsyncIOScheduler | None = None


async def _metering_job():
    from app.services.metering import metering_tick

    await metering_tick()


async def _sync_job():
    from app.services.sync import sync_tick

    await sync_tick()


async def _guard_job():
    from app.services.guard import guard_tick

    await guard_tick()


def start_scheduler() -> AsyncIOScheduler | None:
    global _scheduler
    if not settings.worker_enabled:
        logger.info("WORKER_ENABLED=false，后台任务未启动")
        return None
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(_metering_job, "interval", seconds=settings.metering_interval_seconds, id="metering")
    _scheduler.add_job(_sync_job, "interval", seconds=settings.sync_interval_seconds, id="sync")
    _scheduler.add_job(_guard_job, "interval", seconds=settings.guard_interval_seconds, id="guard")
    _scheduler.start()
    logger.info(
        "后台任务已启动: metering=%ss sync=%ss guard=%ss",
        settings.metering_interval_seconds, settings.sync_interval_seconds, settings.guard_interval_seconds,
    )
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
