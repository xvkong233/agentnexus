"""建表 + 幂等种子数据。"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import hash_password
from app.db import SessionLocal, engine
from app.models import Admin, Base, PricingRule, Setting, Wallet

logger = logging.getLogger("app.seed")

SEED_MODELS = ["glm-5.3", "glm-5.3-flash", "glm-5.3-flashx", "glm-5.3-flashx-legal"]

# 官方推理价（元 / 百万 tokens）。来源: docs.bigmodel.cn/cn/guide/start/pricing（2026-11 查询）
# 缓存存储与沙箱限时免费；Web Search 按次计费（Search-Std 0.01 元/次）
OFFICIAL_PRICING = {
    "glm-5.3": {"input": 8.0, "output": 28.0, "cache_read": 2.0},
    "glm-5.3-flash": {"input": 0.8, "output": 2.8, "cache_read": 0.23},
    "glm-5.3-flashx": {"input": 2.0, "output": 7.0, "cache_read": 0.57},
    "glm-5.3-flashx-legal": {"input": 2.0, "output": 7.0, "cache_read": 0.57},
}
OFFICIAL_WEB_SEARCH_PER_CALL = 0.01


async def seed(db: AsyncSession) -> None:
    # 初始管理员
    admin = (await db.execute(select(Admin).where(Admin.username == settings.first_admin_user))).scalar_one_or_none()
    if not admin:
        db.add(
            Admin(
                username=settings.first_admin_user,
                password_hash=hash_password(settings.first_admin_password),
                display_name="平台管理员",
            )
        )
        logger.info("已创建初始管理员: %s", settings.first_admin_user)

    # 定价规则：写入官方成本价（加价率默认 1，售价=官方价；管理员可调整）
    # 幂等升级：已存在但仍是 0 元占位的规则自动补齐官方价
    for model_id in SEED_MODELS:
        rule = (
            await db.execute(select(PricingRule).where(PricingRule.model_id == model_id))
        ).scalar_one_or_none()
        official = OFFICIAL_PRICING[model_id]
        if not rule:
            db.add(
                PricingRule(
                    model_id=model_id,
                    cost_input_per_m=official["input"],
                    cost_output_per_m=official["output"],
                    cost_cache_read_per_m=official["cache_read"],
                    markup_rate=1,
                    web_search_price_per_call=OFFICIAL_WEB_SEARCH_PER_CALL,
                    note="官方推理价（2026-11）；售价=成本×加价率，请按需调整加价率",
                )
            )
        elif (
            float(rule.cost_input_per_m or 0) == 0
            and float(rule.cost_output_per_m or 0) == 0
            and float(rule.cost_cache_read_per_m or 0) == 0
        ):
            rule.cost_input_per_m = official["input"]
            rule.cost_output_per_m = official["output"]
            rule.cost_cache_read_per_m = official["cache_read"]
            rule.web_search_price_per_call = OFFICIAL_WEB_SEARCH_PER_CALL
            rule.note = "官方推理价（2026-11）自动补齐；售价=成本×加价率"
            logger.info("定价规则 %s 已从占位价升级为官方价", model_id)

    setting = await db.get(Setting, "platform")
    if not setting:
        db.add(Setting(key="platform", value={"seeded_at": "v1"}))

    await db.commit()


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        await seed(db)
