"""内置模拟上游（BIGMODEL_MOCK=true 时启用）。

完整模拟 Managed Agents 的核心行为，便于无真实 API Key 演示/测试：
- Agents / Environments / Sessions / Events CRUD
- 发送 user.message 后异步生成 Agent 回复：status_running → thinking →
  流式 message delta(SSE) → tool_use/result → span.model_request_end(含 model_usage)
  → session.usage 累计快照 → status_idle(end_turn)
- 自定义工具 requires_action 回路、interrupt 打断
- Files / Deployments(含手动触发) / Channels(含微信二维码绑定) / Vaults
"""
import asyncio
import base64
import json
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

from app.core.errors import PlatformError

_PNG_1PX = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d"
        "4944415478da63fccf00ae03050001b5fd78560000000049454e44ae426082"
    )
).decode("ascii")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat().replace("+00:00", "Z")


class _Gen:
    """一个会话内的一次生成过程。"""

    def __init__(self, store: "MockStore", sess: "_MSession", task: asyncio.Task):
        self.store = store
        self.sess = sess
        self.task = task


class _MSession:
    def __init__(self, data: dict):
        self.data = data
        self.events: list[dict] = []           # 持久化事件
        self.stream: list[str] = []            # SSE 帧（含 delta 帧，不持久化）
        self.seq = 0
        self.gen_task: asyncio.Task | None = None
        self.pending_tools: dict[str, asyncio.Event] = {}  # custom_tool_use_id -> Event


class MockStore:
    def __init__(self):
        self.agents: dict[str, dict] = {}
        self.environments: dict[str, dict] = {}
        self.sessions: dict[str, _MSession] = {}
        self.files: dict[str, dict] = {}
        self.file_contents: dict[str, bytes] = {}
        self.deployments: dict[str, dict] = {}
        self.deployment_runs: list[dict] = []
        self.channels: dict[str, dict] = {}
        self.qr_sessions: dict[str, dict] = {}
        self.vaults: dict[str, dict] = {}
        self.credentials: dict[str, list] = {}
        self._id = 0

    def next_id(self, prefix: str) -> str:
        self._id += 1
        return f"{prefix}_mock{self._id:08d}"


STORE = MockStore()


def _err(status: int, etype: str, message: str) -> PlatformError:
    return PlatformError(status, f"upstream_{etype}", message, {"upstream": "mock"})


def _frame(event_type: str | None, data: dict) -> str:
    head = f"event: {event_type}\n" if event_type else ""
    return f"{head}data: {json.dumps(data, ensure_ascii=False)}\n\n"


class MockBigModelClient:
    """与 RealBigModelClient 同接口。api_key 参数仅为兼容工厂签名。"""

    def __init__(self, api_key: str = "mock"):
        self.api_key = api_key

    # ---------- 内部工具 ----------

    async def _not_found(self, store_dict: dict, key: str, what: str) -> dict:
        obj = store_dict.get(key)
        if not obj:
            raise _err(404, "not_found_error", f"{what}不存在: {key}")
        return obj

    async def _persist(self, sess: _MSession, event: dict) -> dict:
        sess.seq += 1
        full = {"id": f"sevt_{sess.data['id']}_{sess.seq:06d}", "processed_at": _iso(), **event}
        sess.events.append(full)
        sess.stream.append(_frame(full["type"], full))
        sess.data["updated_at"] = _iso()
        return full

    def _sse(self, sess: _MSession, event_type: str, data: dict) -> None:
        sess.stream.append(_frame(event_type, data))

    # ---------- Agents ----------

    async def create_agent(self, payload: dict) -> dict:
        aid = STORE.next_id("agent")
        model = payload.get("model", "glm-5.3")
        if isinstance(model, str):
            model = {"id": model, "effort": {"type": "max"}, "speed": "standard"}
        obj = {
            "id": aid,
            "type": "agent",
            "name": payload.get("name", "unnamed"),
            "model": model,
            "system": payload.get("system"),
            "description": payload.get("description"),
            "tools": payload.get("tools", []),
            "skills": payload.get("skills", []),
            "mcp_servers": payload.get("mcp_servers", []),
            "metadata": payload.get("metadata", {}),
            "version": 1,
            "created_at": _iso(),
            "updated_at": _iso(),
            "archived_at": None,
        }
        STORE.agents[aid] = obj
        return dict(obj)

    async def list_agents(self, params: dict | None = None) -> dict:
        params = params or {}
        data = [dict(a) for a in STORE.agents.values()]
        if not params.get("include_archived"):
            data = [a for a in data if not a.get("archived_at")]
        if params.get("limit"):
            data = data[-int(params["limit"]):]
        return {"data": data, "next_page": None}

    async def get_agent(self, agent_id: str) -> dict:
        return dict(await self._not_found(STORE.agents, agent_id, "Agent"))

    async def update_agent(self, agent_id: str, payload: dict) -> dict:
        obj = await self._not_found(STORE.agents, agent_id, "Agent")
        for k in ("name", "system", "description", "tools", "mcp_servers", "skills", "model", "metadata"):
            if k in payload:
                obj[k] = payload[k]
        obj["version"] += 1
        obj["updated_at"] = _iso()
        return dict(obj)

    async def list_agent_versions(self, agent_id: str, params: dict | None = None) -> dict:
        obj = await self._not_found(STORE.agents, agent_id, "Agent")
        versions = []
        for v in range(1, obj["version"] + 1):
            item = dict(obj)
            item["version"] = v
            versions.append(item)
        return {"data": versions, "next_page": None}

    async def archive_agent(self, agent_id: str) -> dict:
        obj = await self._not_found(STORE.agents, agent_id, "Agent")
        obj["archived_at"] = _iso()
        return dict(obj)

    # ---------- Environments ----------

    async def create_environment(self, payload: dict) -> dict:
        eid = STORE.next_id("env")
        config = payload.get("config", {"type": "cloud", "packages": {}, "networking": {"type": "unrestricted"}})
        packages = config.get("packages", {}) or {}
        obj = {
            "id": eid,
            "type": "environment",
            "name": payload.get("name", "unnamed-env"),
            "config": {
                "type": "cloud",
                "packages": {k: list(v or []) for k, v in packages.items()},
                "networking": config.get("networking", {"type": "unrestricted"}),
            },
            "created_at": _iso(),
            "updated_at": _iso(),
            "archived_at": None,
        }
        STORE.environments[eid] = obj
        return dict(obj)

    async def list_environments(self, params: dict | None = None) -> dict:
        return {"data": [dict(e) for e in STORE.environments.values()], "next_page": None}

    async def get_environment(self, environment_id: str) -> dict:
        return dict(await self._not_found(STORE.environments, environment_id, "Environment"))

    async def update_environment(self, environment_id: str, payload: dict) -> dict:
        obj = await self._not_found(STORE.environments, environment_id, "Environment")
        if "name" in payload:
            obj["name"] = payload["name"]
        if "config" in payload:
            obj["config"] = payload["config"]
        obj["updated_at"] = _iso()
        return dict(obj)

    async def archive_environment(self, environment_id: str) -> dict:
        obj = await self._not_found(STORE.environments, environment_id, "Environment")
        obj["archived_at"] = _iso()
        return dict(obj)

    async def delete_environment(self, environment_id: str) -> dict:
        await self._not_found(STORE.environments, environment_id, "Environment")
        STORE.environments.pop(environment_id, None)
        return {}

    # ---------- Sessions ----------

    async def create_session(self, payload: dict) -> dict:
        agent_ref = payload.get("agent") or {}
        agent_id = agent_ref["id"] if isinstance(agent_ref, dict) else agent_ref
        agent = await self._not_found(STORE.agents, agent_id, "Agent")
        version = agent_ref.get("version", agent["version"]) if isinstance(agent_ref, dict) else agent["version"]
        env_id = payload.get("environment_id")
        if not env_id or env_id not in STORE.environments:
            raise _err(400, "invalid_request_error", "environment_id 无效")
        sid = STORE.next_id("sess")
        usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                 "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0}}
        data = {
            "id": sid,
            "type": "session",
            "agent": {"id": agent["id"], "type": "agent", "name": agent["name"],
                      "model": agent["model"], "tools": agent.get("tools", []),
                      "version": version},
            "environment_id": env_id,
            "status": "idle",
            "title": payload.get("title"),
            "metadata": payload.get("metadata", {}),
            "resources": payload.get("resources", []),
            "vault_ids": payload.get("vault_ids", []),
            "budget": None,
            "usage": usage,
            "archived_at": None,
            "created_at": _iso(),
            "updated_at": _iso(),
        }
        sess = _MSession(data)
        STORE.sessions[sid] = sess
        initial = payload.get("initial_events") or []
        if initial:
            for ev in initial:
                if ev.get("type") == "user.message":
                    await self._persist(sess, {"type": "user.message", "content": ev.get("content", [])})
            self._schedule_generation(sess, initial)
        return dict(data)

    async def list_sessions(self, params: dict | None = None) -> dict:
        params = params or {}
        data = [dict(s.data) for s in STORE.sessions.values()]
        if params.get("statuses"):
            wanted = params["statuses"]
            wanted = wanted.split(",") if isinstance(wanted, str) else list(wanted)
            data = [s for s in data if s["status"] in wanted]
        if params.get("agent_id"):
            data = [s for s in data if s["agent"]["id"] == params["agent_id"]]
        data.sort(key=lambda s: s["created_at"], reverse=(params.get("order", "desc") == "desc"))
        limit = int(params.get("limit") or 20)
        page = params.get("page")
        if page:
            try:
                idx = [s["id"] for s in data].index(page)
                data = data[idx:]
            except ValueError:
                data = []
        next_page = data[limit]["id"] if len(data) > limit else None
        return {"data": data[:limit], "next_page": next_page}

    async def get_session(self, session_id: str) -> dict:
        sess = await self._not_found(STORE.sessions, session_id, "Session")
        return dict(sess.data)

    async def update_session(self, session_id: str, payload: dict) -> dict:
        sess = await self._not_found(STORE.sessions, session_id, "Session")
        if "title" in payload:
            sess.data["title"] = payload["title"]
        if "metadata" in payload:
            sess.data["metadata"] = payload["metadata"]
        sess.data["updated_at"] = _iso()
        return dict(sess.data)

    async def archive_session(self, session_id: str) -> dict:
        sess = await self._not_found(STORE.sessions, session_id, "Session")
        if sess.data["status"] == "running":
            raise _err(409, "invalid_request_error", "运行中的会话不能归档")
        sess.data["archived_at"] = _iso()
        return dict(sess.data)

    async def delete_session(self, session_id: str) -> dict:
        sess = await self._not_found(STORE.sessions, session_id, "Session")
        if sess.data["status"] == "running":
            raise _err(409, "invalid_request_error", "运行中的会话不能删除")
        self._cancel_gen(sess)
        STORE.sessions.pop(session_id, None)
        return {"id": session_id, "type": "session_deleted"}

    # ---------- Events ----------

    async def send_events(self, session_id: str, events: list[dict]) -> dict:
        sess = await self._not_found(STORE.sessions, session_id, "Session")
        if not 1 <= len(events) <= 10:
            raise _err(400, "invalid_request_error", "events 数量须为 1-10")
        results = []
        for ev in events:
            etype = ev.get("type", "")
            if etype == "user.message":
                await self._persist(sess, {"type": etype, "content": ev.get("content", [])})
                if sess.data["status"] == "idle":
                    self._schedule_generation(sess, [ev])
            elif etype == "user.interrupt":
                await self._persist(sess, {"type": etype})
                self._interrupt(sess)
            elif etype == "user.custom_tool_result":
                tid = ev.get("custom_tool_use_id", "")
                await self._persist(sess, {"type": etype, "custom_tool_use_id": tid,
                                           "content": ev.get("content", []),
                                           "is_error": bool(ev.get("is_error", False))})
                waiter = sess.pending_tools.pop(tid, None)
                if waiter:
                    waiter.set()
            elif etype == "user.tool_confirmation":
                await self._persist(sess, {"type": etype, **{k: v for k, v in ev.items() if k != "type"}})
            else:
                raise _err(400, "invalid_request_error", f"不支持的事件类型: {etype}")
            results.append({"accepted": True})
        return {"data": results}

    async def list_events(self, session_id: str, params: dict | None = None) -> dict:
        sess = await self._not_found(STORE.sessions, session_id, "Session")
        events = list(sess.events)
        types = params.get("types") if params else None
        if types:
            wanted = types.split(",") if isinstance(types, str) else list(types)
            events = [e for e in events if e["type"] in wanted]
        order = (params or {}).get("order", "asc")
        events.sort(key=lambda e: e["id"], reverse=(order == "desc"))
        limit = int((params or {}).get("limit") or 100)
        page = (params or {}).get("page")
        if page:
            try:
                idx = [e["id"] for e in events].index(page)
                events = events[idx:]
            except ValueError:
                events = []
        next_page = events[limit]["id"] if len(events) > limit else None
        return {"data": events[:limit], "next_page": next_page}

    async def stream_events(self, session_id: str, params: dict | None = None) -> AsyncIterator[bytes]:
        sess = await self._not_found(STORE.sessions, session_id, "Session")
        cursor = len(sess.stream)
        last_ping = time.monotonic()
        while True:
            if cursor < len(sess.stream):
                yield sess.stream[cursor].encode("utf-8")
                cursor = len(sess.stream)
                continue
            if sess.data.get("_closed"):
                return
            if time.monotonic() - last_ping > 15:
                yield b": ping\n\n"
                last_ping = time.monotonic()
            await asyncio.sleep(0.15)

    async def list_threads(self, session_id: str, params: dict | None = None) -> dict:
        await self._not_found(STORE.sessions, session_id, "Session")
        return {"data": [], "next_page": None}

    # ---------- Files ----------

    async def upload_file(self, filename: str, content: bytes, mime_type: str | None = None) -> dict:
        fid = STORE.next_id("file")
        obj = {
            "id": fid,
            "filename": filename,
            "mime_type": mime_type or "application/octet-stream",
            "size_bytes": len(content),
            "downloadable": False,
            "scope": None,
            "created_at": _iso(),
            "expires_at": None,
        }
        STORE.files[fid] = obj
        STORE.file_contents[fid] = content
        return dict(obj)

    async def list_files(self, params: dict | None = None) -> dict:
        params = params or {}
        scope = params.get("scope_id")
        data = [dict(f) for f in STORE.files.values() if not scope or f.get("scope") == scope]
        return {"data": data, "next_page": None}

    async def get_file(self, file_id: str) -> dict:
        return dict(await self._not_found(STORE.files, file_id, "File"))

    async def download_file(self, file_id: str) -> bytes:
        f = await self._not_found(STORE.files, file_id, "File")
        if not f.get("downloadable"):
            raise _err(403, "permission_error", "上传的输入文件不可下载")
        return STORE.file_contents.get(file_id, b"")

    async def delete_file(self, file_id: str) -> dict:
        await self._not_found(STORE.files, file_id, "File")
        STORE.files.pop(file_id, None)
        STORE.file_contents.pop(file_id, None)
        return {"id": file_id, "type": "file_deleted"}

    # ---------- Deployments ----------

    async def create_deployment(self, payload: dict) -> dict:
        did = STORE.next_id("depl")
        agent_ref = payload.get("agent") or {}
        agent_id = agent_ref["id"] if isinstance(agent_ref, dict) else agent_ref
        agent = await self._not_found(STORE.agents, agent_id, "Agent")
        version = agent_ref.get("version", agent["version"]) if isinstance(agent_ref, dict) else agent["version"]
        obj = {
            "id": did,
            "type": "deployment",
            "name": payload.get("name", "unnamed"),
            "agent": {"id": agent["id"], "version": version},
            "environment_id": payload.get("environment_id", ""),
            "schedule": payload.get("schedule"),
            "initial_events": payload.get("initial_events", []),
            "status": "active",
            "created_at": _iso(),
            "updated_at": _iso(),
            "archived_at": None,
        }
        if obj["schedule"]:
            obj["schedule"] = {**obj["schedule"], "upcoming_runs_at": []}
        STORE.deployments[did] = obj
        return dict(obj)

    async def list_deployments(self, params: dict | None = None) -> dict:
        return {"data": [dict(d) for d in STORE.deployments.values()], "next_page": None}

    async def get_deployment(self, deployment_id: str) -> dict:
        return dict(await self._not_found(STORE.deployments, deployment_id, "Deployment"))

    async def update_deployment(self, deployment_id: str, payload: dict) -> dict:
        obj = await self._not_found(STORE.deployments, deployment_id, "Deployment")
        for k in ("name", "schedule", "initial_events"):
            if k in payload:
                obj[k] = payload[k]
        obj["updated_at"] = _iso()
        return dict(obj)

    async def pause_deployment(self, deployment_id: str) -> dict:
        obj = await self._not_found(STORE.deployments, deployment_id, "Deployment")
        obj["status"] = "paused"
        return dict(obj)

    async def unpause_deployment(self, deployment_id: str) -> dict:
        obj = await self._not_found(STORE.deployments, deployment_id, "Deployment")
        obj["status"] = "active"
        return dict(obj)

    async def archive_deployment(self, deployment_id: str) -> dict:
        obj = await self._not_found(STORE.deployments, deployment_id, "Deployment")
        obj["status"] = "archived"
        obj["archived_at"] = _iso()
        return dict(obj)

    async def run_deployment(self, deployment_id: str) -> dict:
        obj = await self._not_found(STORE.deployments, deployment_id, "Deployment")
        run_id = STORE.next_id("drun")
        session = await self.create_session({
            "agent": obj["agent"],
            "environment_id": obj["environment_id"],
            "title": f"定时任务: {obj['name']}",
            "metadata": {"source": "deployment", "deployment_id": deployment_id},
            "initial_events": obj.get("initial_events") or [],
        })
        run = {
            "id": run_id,
            "type": "deployment_run",
            "deployment_id": deployment_id,
            "session_id": session["id"],
            "trigger_type": "manual",
            "trigger_context": {"type": "manual"},
            "status": "succeeded",
            "error": None,
            "created_at": _iso(),
        }
        STORE.deployment_runs.append(run)
        return dict(run)

    async def list_deployment_runs(self, params: dict | None = None) -> dict:
        params = params or {}
        data = list(STORE.deployment_runs)
        if params.get("deployment_id"):
            data = [r for r in data if r["deployment_id"] == params["deployment_id"]]
        return {"data": data, "next_page": None}

    # ---------- Channels ----------

    async def create_channel(self, payload: dict) -> dict:
        cid = STORE.next_id("chan")
        ctype = payload.get("channel_type", "")
        if ctype not in ("feishu", "wecom", "dingtalk", "wechat"):
            raise _err(400, "invalid_request_error", f"不支持的渠道类型: {ctype}")
        bound = ctype != "wechat"
        obj = {
            "id": cid,
            "type": "channel",
            "channel_type": ctype,
            "name": payload.get("name", "unnamed"),
            "template": payload.get("template", {}),
            "channel_config": payload.get("channel_config", {}),
            "binding_status": "bound" if bound else "pending",
            "connection_status": "connected" if bound else "disconnected",
            "last_error": None,
            "enabled": True,
            "created_at": _iso(),
            "updated_at": _iso(),
        }
        STORE.channels[cid] = obj
        return dict(obj)

    async def list_channels(self, params: dict | None = None) -> dict:
        return {"data": [dict(c) for c in STORE.channels.values()], "next_page": None}

    async def get_channel(self, channel_id: str) -> dict:
        return dict(await self._not_found(STORE.channels, channel_id, "Channel"))

    async def patch_channel(self, channel_id: str, payload: dict) -> dict:
        obj = await self._not_found(STORE.channels, channel_id, "Channel")
        if "channel_config" in payload:
            cfg = dict(obj.get("channel_config") or {})
            cfg.update(payload["channel_config"])
            obj["channel_config"] = cfg
        obj["updated_at"] = _iso()
        return dict(obj)

    async def delete_channel(self, channel_id: str) -> dict:
        await self._not_found(STORE.channels, channel_id, "Channel")
        STORE.channels.pop(channel_id, None)
        return {}

    async def create_wechat_qr_session(self, channel_id: str) -> dict:
        await self._not_found(STORE.channels, channel_id, "Channel")
        key = f"qr_{uuid.uuid4().hex[:12]}"
        obj = {"channel_id": channel_id, "session_key": key, "status": "pending",
               "calls": 0,
               "qr_code": "data:image/png;base64," + _PNG_1PX,
               "expires_at": _iso(_now() + timedelta(minutes=8)),
               "created_at": _iso()}
        STORE.qr_sessions[key] = obj
        return dict(obj)

    async def get_wechat_qr_session(self, channel_id: str, session_key: str) -> dict:
        obj = await self._not_found(STORE.qr_sessions, session_key, "QR session")
        obj["calls"] += 1
        if obj["calls"] >= 2 and obj["status"] != "bound":
            obj["status"] = "bound"
            chan = STORE.channels.get(channel_id)
            if chan:
                chan["binding_status"] = "bound"
                chan["connection_status"] = "connected"
        return dict(obj)

    # ---------- Vaults ----------

    async def create_vault(self, payload: dict) -> dict:
        vid = STORE.next_id("vlt")
        obj = {"id": vid, "type": "vault", "display_name": payload.get("display_name", "unnamed"),
               "metadata": payload.get("metadata", {}), "created_at": _iso(), "archived_at": None}
        STORE.vaults[vid] = obj
        STORE.credentials[vid] = []
        return dict(obj)

    async def list_vaults(self, params: dict | None = None) -> dict:
        return {"data": [dict(v) for v in STORE.vaults.values()], "next_page": None}

    async def get_vault(self, vault_id: str) -> dict:
        return dict(await self._not_found(STORE.vaults, vault_id, "Vault"))

    async def update_vault(self, vault_id: str, payload: dict) -> dict:
        obj = await self._not_found(STORE.vaults, vault_id, "Vault")
        for k in ("display_name", "metadata"):
            if k in payload:
                obj[k] = payload[k]
        return dict(obj)

    async def archive_vault(self, vault_id: str) -> dict:
        obj = await self._not_found(STORE.vaults, vault_id, "Vault")
        obj["archived_at"] = _iso()
        return dict(obj)

    async def delete_vault(self, vault_id: str) -> dict:
        await self._not_found(STORE.vaults, vault_id, "Vault")
        STORE.vaults.pop(vault_id, None)
        STORE.credentials.pop(vault_id, None)
        return {}

    async def add_credential(self, vault_id: str, payload: dict) -> dict:
        await self._not_found(STORE.vaults, vault_id, "Vault")
        cid = STORE.next_id("vcrd")
        auth = payload.get("auth", {})
        cred = {
            "id": cid, "name": payload.get("name", "credential"), "auth": {"type": auth.get("type")},
            "created_at": _iso(), "archived_at": None,
        }
        STORE.credentials[vault_id].append({"meta": cred, "secret": payload})
        return cred

    async def list_credentials(self, vault_id: str, params: dict | None = None) -> dict:
        await self._not_found(STORE.vaults, vault_id, "Vault")
        return {"data": [dict(c["meta"]) for c in STORE.credentials.get(vault_id, [])], "next_page": None}

    async def get_credential(self, vault_id: str, credential_id: str) -> dict:
        for c in STORE.credentials.get(vault_id, []):
            if c["meta"]["id"] == credential_id:
                return dict(c["meta"])
        raise _err(404, "not_found_error", "凭据不存在")

    async def update_credential(self, vault_id: str, credential_id: str, payload: dict) -> dict:
        for c in STORE.credentials.get(vault_id, []):
            if c["meta"]["id"] == credential_id:
                c["secret"] = {**c["secret"], **payload}
                return dict(c["meta"])
        raise _err(404, "not_found_error", "凭据不存在")

    async def archive_credential(self, vault_id: str, credential_id: str) -> dict:
        for c in STORE.credentials.get(vault_id, []):
            if c["meta"]["id"] == credential_id:
                c["meta"]["archived_at"] = _iso()
                return dict(c["meta"])
        raise _err(404, "not_found_error", "凭据不存在")

    async def delete_credential(self, vault_id: str, credential_id: str) -> dict:
        creds = STORE.credentials.get(vault_id, [])
        STORE.credentials[vault_id] = [c for c in creds if c["meta"]["id"] != credential_id]
        return {"id": credential_id, "type": "credential_deleted"}

    # ---------- 会话生成（模拟 Agent 循环） ----------

    def _cancel_gen(self, sess: _MSession) -> None:
        if sess.gen_task and not sess.gen_task.done():
            sess.gen_task.cancel()
        sess.gen_task = None

    def _interrupt(self, sess: _MSession) -> None:
        self._cancel_gen(sess)
        sess.data["status"] = "idle"

        async def _finish():
            await self._persist(sess, {"type": "session.status_idle",
                                       "stop_reason": {"type": "end_turn"}})
            sess.data["status"] = "idle"

        asyncio.get_running_loop().create_task(_finish())

    def _schedule_generation(self, sess: _MSession, user_events: list[dict]) -> None:
        self._cancel_gen(sess)
        sess.data["status"] = "running"
        sess.gen_task = asyncio.get_running_loop().create_task(self._generate(sess, user_events))

    def _agent_tools(self, sess: _MSession) -> list[dict]:
        tools = (sess.data.get("agent") or {}).get("tools") or []
        if isinstance(tools, str):
            try:
                tools = json.loads(tools)
            except Exception:
                tools = []
        return tools if isinstance(tools, list) else []

    def _model_id(self, sess: _MSession) -> str:
        model = (sess.data.get("agent") or {}).get("model") or {}
        return model.get("id", "glm-5.3") if isinstance(model, dict) else str(model)

    def _text_of(self, ev: dict) -> str:
        out = []
        for block in ev.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                out.append(block.get("text", ""))
            elif isinstance(block, str):
                out.append(block)
        return " ".join(out)

    async def _generate(self, sess: _MSession, user_events: list[dict]) -> None:
        try:
            await self._persist(sess, {"type": "session.status_running"})
            await asyncio.sleep(random.uniform(0.3, 0.8))

            question = " ".join(self._text_of(e) for e in user_events).strip()
            model_id = self._model_id(sess)
            tools = self._agent_tools(sess)
            has_toolset = any(t.get("type") == "agent_toolset_20260601" for t in tools)
            custom_tools = [t for t in tools if t.get("type") == "custom"]

            # 偶尔执行一次内置工具展示工具卡
            if has_toolset and random.random() < 0.5:
                tool_id = STORE.next_id("sevt")
                await self._persist(sess, {"type": "agent.tool_use", "name": "bash",
                                           "input": {"command": "echo 'working on it…'"},
                                           "evaluated_permission": {"type": "always_allow"}})
                await asyncio.sleep(random.uniform(0.3, 0.7))
                await self._persist(sess, {"type": "agent.tool_result", "name": "bash",
                                           "output": [{"type": "text", "text": "working on it…"}],
                                           "is_error": False})

            # 自定义工具：needs info → requires_action
            if custom_tools and random.random() < 0.6:
                tool = random.choice(custom_tools)
                tid = STORE.next_id("sevt_ctool")
                await self._persist(sess, {"type": "agent.custom_tool_use", "id": tid,
                                           "name": tool.get("name", "custom"),
                                           "input": {"question": question[:200] or "(empty)"}})
                sess.pending_tools[tid] = asyncio.Event()
                await self._persist(sess, {"type": "session.status_idle",
                                           "stop_reason": {"type": "requires_action", "event_ids": [tid]}})
                sess.data["status"] = "idle"
                try:
                    await asyncio.wait_for(sess.pending_tools[tid].wait(), timeout=120)
                except asyncio.TimeoutError:
                    sess.pending_tools.pop(tid, None)
                    return
                sess.data["status"] = "running"
                await self._persist(sess, {"type": "session.status_running"})
                await asyncio.sleep(random.uniform(0.4, 1.0))

            # 思考
            if random.random() < 0.7:
                await asyncio.sleep(random.uniform(0.2, 0.5))
                await self._persist(sess, {"type": "agent.thinking",
                                           "content": [{"type": "text",
                                                        "text": f"分析请求：「{question[:40]}」，整理回答思路…"}]})

            # 流式回复（delta 帧，不持久化）
            answer = self._compose_answer(question, model_id)
            msg_id = STORE.next_id("sevt_msg")
            self._sse(sess, "event_start",
                      {"type": "event_start", "event": {"type": "agent.message", "id": msg_id}})
            await self._persist(sess, {"type": "span.model_request_start", "model": model_id})
            for chunk in _split_chunks(answer):
                self._sse(sess, "event_delta",
                          {"type": "event_delta", "event_type": "agent.message",
                           "event_id": msg_id, "content_delta": {"type": "text", "text": chunk}})
                await asyncio.sleep(random.uniform(0.05, 0.18))

            # 计量
            input_tokens = 180 + max(8, len(question)) * 2
            output_tokens = 240 + len(answer) * 2 + random.randint(0, 120)
            cache_read = random.choice([0, 0, random.randint(100, 2500)])
            web_search = 1 if (has_toolset and random.random() < 0.2) else 0

            await self._persist(sess, {"type": "agent.message",
                                       "content": [{"type": "text", "text": answer}]})
            await self._persist(sess, {
                "type": "span.model_request_end", "model": model_id, "is_error": False,
                "model_usage": {"input_tokens": input_tokens, "output_tokens": output_tokens,
                                "cache_read_input_tokens": cache_read, "model": model_id},
            })

            usage = sess.data["usage"]
            usage["input_tokens"] += input_tokens
            usage["output_tokens"] += output_tokens
            usage["cache_read_input_tokens"] += cache_read
            usage["server_tool_use"]["web_search_requests"] += web_search
            await self._persist(sess, {"type": "session.usage", "usage": json.loads(json.dumps(usage))})

            # 偶尔产出文件
            if has_toolset and random.random() < 0.15:
                fid = STORE.next_id("file")
                content = f"Session 产物示例（{sess.data['id']}）\n问题: {question}\n回答: {answer}\n".encode("utf-8")
                STORE.files[fid] = {"id": fid, "filename": "output-summary.txt",
                                    "mime_type": "text/plain", "size_bytes": len(content),
                                    "downloadable": True, "scope": sess.data["id"],
                                    "created_at": _iso(), "expires_at": None}
                STORE.file_contents[fid] = content

            await self._persist(sess, {"type": "session.status_idle",
                                       "stop_reason": {"type": "end_turn"}, "stop_details": None})
            sess.data["status"] = "idle"
        except asyncio.CancelledError:
            raise
        except Exception:
            import logging

            logging.getLogger("app.bigmodel.mock").exception("模拟生成失败: %s", sess.data["id"])
            sess.data["status"] = "idle"

    def _compose_answer(self, question: str, model_id: str) -> str:
        q = question or "（空输入）"
        return (
            f"你好！我是在云端沙箱中运行的模拟 Agent（模型 {model_id}）。\n\n"
            f"关于「{q[:80]}」，这里是模拟环境生成的回复：\n\n"
            "1. 平台已完成计量：本次回复的 token 用量会写入计费流水并从钱包扣减；\n"
            "2. 会话事件通过 SSE 流式回传，你看到的是逐段到达的增量；\n"
            "3. 将 .env 中 BIGMODEL_MOCK 改为 false 并在管理端配置平台密钥，"
            "即可切换到真实的智谱 Managed Agents。\n\n"
            "需要我做点什么，请继续发送消息。"
        )

    def _compose_chunks(self, answer: str):
        return _split_chunks(answer)


def _split_chunks(text: str, size: int = 24):
    for i in range(0, len(text), size):
        yield text[i:i + size]
