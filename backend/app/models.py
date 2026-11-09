"""全部 ORM 模型。金额一律 Numeric + Decimal，杜绝浮点误差。"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

MONEY = Numeric(18, 6)
PRICE = Numeric(18, 6)


def uid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    display_name: Mapped[str] = mapped_column(String(64), default="管理员")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Tenant(Base):
    """客户（租户）。"""
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(128))
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    contact_name: Mapped[str] = mapped_column(String(64), default="")
    contact_phone: Mapped[str] = mapped_column(String(32), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    # active / suspended
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    # 余额低于该值视为欠费停服阈值（含 0 = 余额归零即停）
    low_balance_threshold: Mapped[float] = mapped_column(MONEY, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TenantUser(Base):
    """客户门户登录账号。"""
    __tablename__ = "tenant_users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    display_name: Mapped[str] = mapped_column(String(64), default="")
    role: Mapped[str] = mapped_column(String(32), default="owner")  # owner / member
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Wallet(Base):
    """租户钱包，行级锁保证扣费一致性。"""
    __tablename__ = "wallets"
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), primary_key=True)
    balance: Mapped[float] = mapped_column(MONEY, default=0)
    # 欠费自动封锁（guard 置位，充值后解除）
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_reason: Mapped[str] = mapped_column(String(256), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    # recharge / adjust / consumption / refund
    type: Mapped[str] = mapped_column(String(32), index=True)
    # 正负带符号金额
    amount: Mapped[float] = mapped_column(MONEY)
    balance_after: Mapped[float] = mapped_column(MONEY)
    ref_type: Mapped[str] = mapped_column(String(64), default="")
    ref_id: Mapped[str] = mapped_column(String(128), default="")
    note: Mapped[str] = mapped_column(String(512), default="")
    operator: Mapped[str] = mapped_column(String(128), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class PricingRule(Base):
    """按模型的定价规则：售价 = 官方成本价 × 加价率。单位：元 / 百万 token。"""
    __tablename__ = "pricing_rules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    model_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    cost_input_per_m: Mapped[float] = mapped_column(PRICE, default=0)
    cost_output_per_m: Mapped[float] = mapped_column(PRICE, default=0)
    cost_cache_read_per_m: Mapped[float] = mapped_column(PRICE, default=0)
    markup_rate: Mapped[float] = mapped_column(Numeric(8, 4), default=1)
    # web_search 每次调用售价（元）
    web_search_price_per_call: Mapped[float] = mapped_column(PRICE, default=0)
    note: Mapped[str] = mapped_column(String(512), default="")
    updated_by: Mapped[str] = mapped_column(String(128), default="system")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PlatformKey(Base):
    """平台持有的上游 BigModel API Key（Fernet 加密落库，仅回显前缀）。"""
    __tablename__ = "platform_keys"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(128))
    encrypted_key: Mapped[str] = mapped_column(Text)
    key_hint: Mapped[str] = mapped_column(String(32), default="")
    # 绑定租户：该租户的上游调用走此 Key（用于上游侧费用归属）；空 = 平台池
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TenantApiKey(Base):
    """发放给客户的开放平台 API Key（sha256 哈希存储，明文仅创建时返回一次）。"""
    __tablename__ = "tenant_api_keys"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), default="default")
    prefix: Mapped[str] = mapped_column(String(32), index=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UsageRecord(Base):
    """计量流水（计费明细行）。单价快照随行保存，历史账单不受改价影响。"""
    __tablename__ = "usage_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sessions.id"), nullable=True)
    upstream_session_id: Mapped[str] = mapped_column(String(128), default="")
    model_id: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(32), default="")  # web_chat/open_api/deployment/channel/unknown
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    web_search_requests: Mapped[int] = mapped_column(Integer, default=0)
    cost_input: Mapped[float] = mapped_column(MONEY, default=0)
    cost_output: Mapped[float] = mapped_column(MONEY, default=0)
    cost_cache: Mapped[float] = mapped_column(MONEY, default=0)
    cost_search: Mapped[float] = mapped_column(MONEY, default=0)
    cost_total: Mapped[float] = mapped_column(MONEY, default=0)
    price_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    metered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_usage_tenant_time", "tenant_id", "created_at"),
    )


class Agent(Base):
    """Agent 定义（本地镜像上游）。"""
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    upstream_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    model_id: Mapped[str] = mapped_column(String(64), default="glm-5.3-flash", index=True)
    model_config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    system: Mapped[str] = mapped_column(Text, default="")
    tools: Mapped[list] = mapped_column(JSON, default=list)
    mcp_servers: Mapped[list] = mapped_column(JSON, default=list)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    upstream_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)  # active/archived
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Environment(Base):
    __tablename__ = "environments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    upstream_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Session(Base):
    """会话（本地镜像 + 计量缓存）。"""
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    upstream_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("agents.id"), nullable=True)
    upstream_agent_id: Mapped[str] = mapped_column(String(128), default="")
    upstream_env_id: Mapped[str] = mapped_column(String(128), default="")
    title: Mapped[str] = mapped_column(String(256), default="")
    # web_chat / open_api / deployment / channel / imported
    source: Mapped[str] = mapped_column(String(32), default="web_chat", index=True)
    channel_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("channels.id"), nullable=True)
    deployment_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("deployments.id"), nullable=True)
    model_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    # idle / running / rescheduling / terminated
    status: Mapped[str] = mapped_column(String(32), default="idle", index=True)
    # 计量缓存（上游累计快照）
    usage_input: Mapped[int] = mapped_column(BigInteger, default=0)
    usage_output: Mapped[int] = mapped_column(BigInteger, default=0)
    usage_cache_read: Mapped[int] = mapped_column(BigInteger, default=0)
    usage_web_search: Mapped[int] = mapped_column(Integer, default=0)
    cost_total: Mapped[float] = mapped_column(MONEY, default=0)
    last_metered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    upstream_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    __table_args__ = (
        Index("ix_sessions_tenant_created", "tenant_id", "created_at"),
        Index("ix_sessions_metering", "status", "last_metered_at"),
    )


class Deployment(Base):
    __tablename__ = "deployments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    upstream_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"))
    upstream_env_id: Mapped[str] = mapped_column(String(128), default="")
    name: Mapped[str] = mapped_column(String(256))
    schedule: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    initial_events: Mapped[list] = mapped_column(JSON, default=list)
    # active / paused / archived
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    # 由守护任务因欠费自动暂停（余额恢复后自动解除）
    paused_by_guard: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Channel(Base):
    """聊天渠道（feishu / wecom / dingtalk / wechat）。凭据由上游托管，平台不落库。"""
    __tablename__ = "channels"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    upstream_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    channel_type: Mapped[str] = mapped_column(String(32), index=True)  # feishu/wecom/dingtalk/wechat
    name: Mapped[str] = mapped_column(String(256))
    template: Mapped[dict] = mapped_column(JSON, default=dict)
    binding_status: Mapped[str] = mapped_column(String(32), default="")
    connection_status: Mapped[str] = mapped_column(String(32), default="")
    last_error: Mapped[str] = mapped_column(Text, default="")
    # active / deleted
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Vault(Base):
    __tablename__ = "vaults"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    upstream_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ToolWebhook(Base):
    """租户自定义工具执行回调：平台将 agent.custom_tool_use HMAC 签名转发到此 URL 并代回结果。"""
    __tablename__ = "tool_webhooks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), unique=True)
    url: Mapped[str] = mapped_column(String(512), default="")
    secret: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_type: Mapped[str] = mapped_column(String(32), default="admin")  # admin/tenant/system
    actor_id: Mapped[str] = mapped_column(String(64), default="")
    actor_name: Mapped[str] = mapped_column(String(128), default="")
    action: Mapped[str] = mapped_column(String(128), index=True)
    target_type: Mapped[str] = mapped_column(String(64), default="")
    target_id: Mapped[str] = mapped_column(String(128), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
