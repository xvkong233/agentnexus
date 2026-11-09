"""端到端冒烟：SQLite + Mock 上游跑通 计费→聊天→计量→扣款→开放API 全链路。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.update({
    "DATABASE_URL": "sqlite+aiosqlite:///./smoke.db",
    "BIGMODEL_MOCK": "true",
    "WORKER_ENABLED": "false",
    "SECRET_KEY": "smoke-secret",
    "MASTER_KEY": "smoke-master",
    "FIRST_ADMIN_USER": "admin",
    "FIRST_ADMIN_PASSWORD": "admin123456",
})
if os.path.exists("./smoke.db"):
    os.remove("./smoke.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402



def main() -> None:
    with TestClient(app) as client:
        _run(client)


def _run(client) -> None:
    # ---------- 管理员 ----------
    r = client.post("/api/admin/auth/login", json={"username": "admin", "password": "admin123456"})
    assert r.status_code == 200, r.text
    admin_token = r.json()["token"]
    H = {"Authorization": f"Bearer {admin_token}"}
    print("[1] 管理员登录 OK")

    # ---------- 创建租户 + 门户账号 + 赠送余额 ----------
    r = client.post(
        "/api/admin/tenants",
        headers=H,
        json={
            "name": "测试客户A", "code": "cust-a",
            "portal_username": "usera", "portal_password": "pass123456",
            "initial_balance": 100,
        },
    )
    assert r.status_code == 200, r.text
    tenant_id = r.json()["id"]
    assert r.json()["balance"] == 100.0
    print("[2] 创建租户+赠送 ¥100 OK")

    # ---------- 配置定价 ----------
    r = client.put(
        "/api/admin/pricing/glm-5.3-flash",
        headers=H,
        json={"cost_input_per_m": 2, "cost_output_per_m": 8, "cost_cache_read_per_m": 0.2,
              "markup_rate": 1.5, "web_search_price_per_call": 0.03},
    )
    assert r.status_code == 200, r.text
    assert abs(r.json()["sale_output_per_m"] - 12.0) < 1e-6
    print("[3] 定价配置 OK（售价=成本×1.5）")

    # ---------- 门户登录 ----------
    r = client.post("/api/portal/auth/login", json={"username": "usera", "password": "pass123456"})
    assert r.status_code == 200, r.text
    P = {"Authorization": f"Bearer {r.json()['token']}"}
    print("[4] 门户登录 OK")

    # ---------- 创建环境 + Agent ----------
    r = client.post("/api/portal/environments", headers=P,
                    json={"name": "基础环境", "pip": ["pandas"]})
    assert r.status_code == 200, r.text
    env_id = r.json()["id"]
    r = client.post("/api/portal/agents", headers=P, json={
        "name": "客服助手",
        "model": {"id": "glm-5.3-flash", "effort": "high"},
        "system": "你是一个有帮助的客服。",
        "tools": [{"type": "agent_toolset_20260601"}],
    })
    assert r.status_code == 200, r.text
    agent_id = r.json()["id"]
    print("[5] 创建环境+Agent OK")

    # ---------- 创建会话 + 发消息 ----------
    r = client.post("/api/portal/sessions", headers=P, json={
        "agent_id": agent_id, "environment_id": env_id,
        "title": "冒烟测试会话", "initial_message": "你好，请介绍一下平台计费方式",
    })
    assert r.status_code == 200, r.text
    session_id = r.json()["id"]
    assert r.json()["status"] in ("idle", "running")
    print("[6] 创建会话 OK（含初始消息，模拟生成已启动）")

    # 等模拟生成完成
    for _ in range(60):
        time.sleep(0.5)
        r = client.get(f"/api/portal/sessions/{session_id}", headers=P)
        if r.json().get("status") == "idle" and r.json()["usage"]["output_tokens"] > 0:
            break
    assert r.json()["usage"]["output_tokens"] > 0, "模拟生成未产生用量"
    print("[7] 模拟生成完成，用量:", r.json()["usage"])

    # 等计量任务（手动触发一次计量逻辑）
    import asyncio
    from app.services.metering import metering_tick

    ticked = asyncio.get_event_loop().run_until_complete(metering_tick()) if False else None
    # TestClient 环境下直接同步调用
    asyncio.run(metering_tick())
    asyncio.run(metering_tick())

    # 检查钱包扣减与流水
    r = client.get("/api/portal/wallet", headers=P)
    balance = r.json()["balance"]
    assert balance < 100, f"钱包未扣减: {balance}"
    r = client.get("/api/portal/usage-records", headers=P)
    assert r.json()["total"] >= 1
    rec = r.json()["items"][0]
    assert rec["cost_total"] > 0
    print(f"[8] 计量扣款 OK：余额 ¥{balance}，流水费用 ¥{rec['cost_total']}（单价快照={rec['price_snapshot']}）")

    # 事件历史
    r = client.get(f"/api/portal/sessions/{session_id}/events", headers=P, params={"limit": 200})
    types = {e["type"] for e in r.json()["data"]}
    assert "agent.message" in types and "session.usage" in types and "session.status_idle" in types
    print("[9] 事件历史 OK：", sorted(types))

    # ---------- 管理端视角 ----------
    r = client.get("/api/admin/usage-records", headers=H)
    assert r.json()["total"] >= 1
    r = client.get("/api/admin/dashboard", headers=H)
    assert r.json()["month_cost"] > 0
    print("[10] 管理端用量/仪表盘 OK")

    # ---------- 开放 API ----------
    r = client.post("/api/portal/api-keys", headers=P, json={"name": "集成测试"})
    assert r.status_code == 200, r.text
    open_key = r.json()["api_key"]
    OK = {"X-API-Key": open_key}
    r = client.get("/api/open/v1/wallet", headers=OK)
    assert r.status_code == 200, r.text
    r = client.post("/api/open/v1/sessions", headers=OK, json={
        "agent_id": agent_id, "environment_id": env_id, "title": "开放API会话",
    })
    assert r.status_code == 200, r.text
    open_session = r.json()["id"]
    r = client.post(f"/api/open/v1/sessions/{open_session}/messages", headers=OK,
                    json={"text": "通过开放API问一个问题"})
    assert r.status_code == 200, r.text
    for _ in range(40):
        time.sleep(0.5)
        r = client.get(f"/api/open/v1/sessions/{open_session}", headers=OK)
        if r.json()["status"] == "idle" and r.json()["usage"]["output_tokens"] > 0:
            break
    assert r.json()["usage"]["output_tokens"] > 0
    asyncio.run(metering_tick())
    r = client.get("/api/open/v1/usage/records", headers=OK)
    assert r.json()["total"] >= 2
    print("[11] 开放API 全链路 OK（建会话→发消息→计量入账）")

    # ---------- 定时任务 ----------
    r = client.post("/api/portal/deployments", headers=P, json={
        "agent_id": agent_id, "environment_id": env_id, "name": "每日摘要",
        "schedule": {"type": "cron", "expression": "0 9 * * 1-5", "timezone": "Asia/Shanghai"},
        "initial_message": "生成昨日摘要",
    })
    assert r.status_code == 200, r.text
    dep_id = r.json()["id"]
    r = client.post(f"/api/portal/deployments/{dep_id}/run", headers=P)
    assert r.status_code == 200, r.text
    print("[12] 定时任务创建+手动触发 OK")

    # ---------- 渠道（个人微信二维码流程） ----------
    r = client.post("/api/portal/channels", headers=P, json={
        "channel_type": "wechat", "name": "客服微信号",
        "agent_id": agent_id, "environment_id": env_id,
    })
    assert r.status_code == 200, r.text
    ch = r.json()
    assert ch.get("qr", {}).get("qr_code", "").startswith("data:image")
    qr_key = ch["qr"]["session_key"]
    r = client.get(f"/api/portal/channels/{ch['id']}/qr-session/{qr_key}", headers=P)
    r = client.get(f"/api/portal/channels/{ch['id']}/qr-session/{qr_key}", headers=P)
    assert r.json()["status"] == "bound"
    r = client.post("/api/portal/channels", headers=P, json={
        "channel_type": "feishu", "name": "飞书机器人",
        "agent_id": agent_id, "environment_id": env_id,
        "credentials": {"app_id": "cli_x", "app_secret": "s"},
    })
    assert r.status_code == 200
    print("[13] 渠道 OK（微信二维码绑定 + 飞书凭据创建）")

    # ---------- 欠费封锁 ----------
    r = client.post(f"/api/admin/tenants/{tenant_id}/adjust", headers=H,
                    json={"amount": -1000, "note": "测试欠费"})
    assert r.status_code == 200
    from app.services.guard import guard_tick

    asyncio.run(guard_tick())
    r = client.get("/api/portal/wallet", headers=P)
    assert r.json()["blocked"] is True
    r = client.post(f"/api/open/v1/sessions/{open_session}/messages", headers=OK, json={"text": "x"})
    assert r.status_code == 402, f"期望402，实际 {r.status_code}"
    r = client.get(f"/api/portal/deployments/{dep_id}", headers=P)
    assert r.json()["paused_by_guard"] is True and r.json()["status"] == "paused"
    print("[14] 欠费封锁 OK：消息402、定时任务被自动暂停")

    # 充值恢复
    r = client.post(f"/api/admin/tenants/{tenant_id}/recharge", headers=H, json={"amount": 2000})
    asyncio.run(guard_tick())
    r = client.get(f"/api/portal/deployments/{dep_id}", headers=P)
    assert r.json()["status"] == "active" and r.json()["paused_by_guard"] is False
    print("[15] 充值自动恢复 OK")

    print("\n=== 冒烟测试全部通过 ===")


if __name__ == "__main__":
    main()
