"""智谱 Managed Agents 真实 HTTP 客户端。

参考文档: https://docs.bigmodel.cn/cn/managed-agents/api-reference
- 基址: {BIGMODEL_BASE_URL}  (渠道 API 使用独立的 forward/v0 基址)
- 请求头: Authorization Bearer + zai-version + zai-beta（缺一不可）
- 错误信封: {"error": {"type", "message"}, "request_id"}
- 429/5xx 按指数退避重试；SSE 流式接口不做重试
"""
import asyncio
import json
import logging
import random
from typing import Any, AsyncIterator

import httpx

from app.config import settings
from app.core.errors import upstream_error

logger = logging.getLogger("app.bigmodel")

RETRYABLE_STATUS = {429, 502, 503, 504, 529}


class RealBigModelClient:
    """按所选 API Key 构造；所有路径以 /v1 开头（渠道 API 除外）。"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base = settings.bigmodel_base_url.rstrip("/")
        self.channel_base = settings.bigmodel_channel_base_url.rstrip("/")
        self.timeout = settings.http_timeout_seconds

    # ---------- 基础设施 ----------

    def _headers(self, extra: dict | None = None) -> dict:
        h = {
            "Authorization": f"Bearer {self.api_key}",
            "zai-version": settings.zai_version,
            "zai-beta": settings.zai_beta,
        }
        if extra:
            h.update(extra)
        return h

    @staticmethod
    def _map_error(status: int, body: bytes) -> Exception:
        code, message, request_id = "api_error", body.decode("utf-8", "replace")[:500], ""
        try:
            data = json.loads(body)
            err = data.get("error") or {}
            code = err.get("type") or code
            message = err.get("message") or message
            request_id = data.get("request_id") or ""
        except Exception:
            pass
        return upstream_error(status, code, message, {"request_id": request_id, "http_status": status})

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: dict | None = None,
        files: Any = None,
        data: dict | None = None,
        base: str | None = None,
        retry: bool = True,
    ) -> Any:
        url = f"{base or self.base}{path}"
        headers = self._headers({"Accept": "application/json"})
        attempts = 3 if retry else 1
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.request(
                        method, url, params=params, json=json_body, files=files, data=data, headers=headers
                    )
                if resp.status_code < 400:
                    if resp.status_code == 204 or not resp.content:
                        return {}
                    return resp.json()
                if resp.status_code in RETRYABLE_STATUS and attempt < attempts - 1:
                    delay = 0.5 * (2**attempt) + random.random() * 0.3
                    logger.warning("上游 %s %s -> %s，%.1fs 后重试", method, path, resp.status_code, delay)
                    await asyncio.sleep(delay)
                    continue
                raise self._map_error(resp.status_code, resp.content)
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt < attempts - 1:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise upstream_error(502, "transport_error", f"上游连接失败: {exc}") from exc
        raise last_exc or upstream_error(502, "unknown", "上游请求失败")

    @staticmethod
    def _clean_params(params: dict | None) -> dict | None:
        if not params:
            return None
        return {k: v for k, v in params.items() if v is not None}

    # ---------- Agents ----------

    async def create_agent(self, payload: dict) -> dict:
        return await self._request("POST", "/v1/agents", json_body=payload)

    async def list_agents(self, params: dict | None = None) -> dict:
        return await self._request("GET", "/v1/agents", params=self._clean_params(params))

    async def get_agent(self, agent_id: str) -> dict:
        return await self._request("GET", f"/v1/agents/{agent_id}")

    async def update_agent(self, agent_id: str, payload: dict) -> dict:
        return await self._request("POST", f"/v1/agents/{agent_id}", json_body=payload)

    async def list_agent_versions(self, agent_id: str, params: dict | None = None) -> dict:
        return await self._request("GET", f"/v1/agents/{agent_id}/versions", params=self._clean_params(params))

    async def archive_agent(self, agent_id: str) -> dict:
        return await self._request("POST", f"/v1/agents/{agent_id}/archive", json_body={})

    # ---------- Environments ----------

    async def create_environment(self, payload: dict) -> dict:
        return await self._request("POST", "/v1/environments", json_body=payload)

    async def list_environments(self, params: dict | None = None) -> dict:
        return await self._request("GET", "/v1/environments", params=self._clean_params(params))

    async def get_environment(self, environment_id: str) -> dict:
        return await self._request("GET", f"/v1/environments/{environment_id}")

    async def update_environment(self, environment_id: str, payload: dict) -> dict:
        return await self._request("POST", f"/v1/environments/{environment_id}", json_body=payload)

    async def archive_environment(self, environment_id: str) -> dict:
        return await self._request("POST", f"/v1/environments/{environment_id}/archive", json_body={})

    async def delete_environment(self, environment_id: str) -> dict:
        return await self._request("DELETE", f"/v1/environments/{environment_id}")

    # ---------- Sessions ----------

    async def create_session(self, payload: dict) -> dict:
        return await self._request("POST", "/v1/sessions", json_body=payload)

    async def list_sessions(self, params: dict | None = None) -> dict:
        return await self._request("GET", "/v1/sessions", params=self._clean_params(params))

    async def get_session(self, session_id: str) -> dict:
        return await self._request("GET", f"/v1/sessions/{session_id}")

    async def update_session(self, session_id: str, payload: dict) -> dict:
        return await self._request("POST", f"/v1/sessions/{session_id}", json_body=payload)

    async def archive_session(self, session_id: str) -> dict:
        return await self._request("POST", f"/v1/sessions/{session_id}/archive", json_body={})

    async def delete_session(self, session_id: str) -> dict:
        return await self._request("DELETE", f"/v1/sessions/{session_id}")

    # ---------- Events ----------

    async def send_events(self, session_id: str, events: list[dict]) -> dict:
        return await self._request(
            "POST", f"/v1/sessions/{session_id}/events", json_body={"events": events}, retry=False
        )

    async def list_events(self, session_id: str, params: dict | None = None) -> dict:
        return await self._request("GET", f"/v1/sessions/{session_id}/events", params=self._clean_params(params))

    async def stream_events(self, session_id: str, params: dict | None = None) -> AsyncIterator[bytes]:
        """SSE 实时流（live-only）。返回原始字节块，由上层直接转发给浏览器。"""
        url = f"{self.base}/v1/sessions/{session_id}/events/stream"
        headers = self._headers({"Accept": "text/event-stream"})
        timeout = httpx.Timeout(self.timeout, read=None)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("GET", url, params=self._clean_params(params), headers=headers) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise self._map_error(resp.status_code, body)
                async for chunk in resp.aiter_raw():
                    yield chunk

    async def list_threads(self, session_id: str, params: dict | None = None) -> dict:
        return await self._request("GET", f"/v1/sessions/{session_id}/threads", params=self._clean_params(params))

    # ---------- Files ----------

    async def upload_file(self, filename: str, content: bytes, mime_type: str | None = None) -> dict:
        files = {"file": (filename, content, mime_type or "application/octet-stream")}
        return await self._request("POST", "/v1/files", files=files, retry=False)

    async def list_files(self, params: dict | None = None) -> dict:
        return await self._request("GET", "/v1/files", params=self._clean_params(params))

    async def get_file(self, file_id: str) -> dict:
        return await self._request("GET", f"/v1/files/{file_id}")

    async def download_file(self, file_id: str) -> bytes:
        url = f"{self.base}/v1/files/{file_id}/content"
        headers = self._headers()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code >= 400:
            raise self._map_error(resp.status_code, resp.content)
        return resp.content

    async def delete_file(self, file_id: str) -> dict:
        return await self._request("DELETE", f"/v1/files/{file_id}")

    # ---------- Deployments ----------

    async def create_deployment(self, payload: dict) -> dict:
        return await self._request("POST", "/v1/deployments", json_body=payload)

    async def list_deployments(self, params: dict | None = None) -> dict:
        return await self._request("GET", "/v1/deployments", params=self._clean_params(params))

    async def get_deployment(self, deployment_id: str) -> dict:
        return await self._request("GET", f"/v1/deployments/{deployment_id}")

    async def update_deployment(self, deployment_id: str, payload: dict) -> dict:
        return await self._request("POST", f"/v1/deployments/{deployment_id}", json_body=payload)

    async def pause_deployment(self, deployment_id: str) -> dict:
        return await self._request("POST", f"/v1/deployments/{deployment_id}/pause", json_body={})

    async def unpause_deployment(self, deployment_id: str) -> dict:
        return await self._request("POST", f"/v1/deployments/{deployment_id}/unpause", json_body={})

    async def archive_deployment(self, deployment_id: str) -> dict:
        return await self._request("POST", f"/v1/deployments/{deployment_id}/archive", json_body={})

    async def run_deployment(self, deployment_id: str) -> dict:
        return await self._request("POST", f"/v1/deployments/{deployment_id}/run", json_body={}, retry=False)

    async def list_deployment_runs(self, params: dict | None = None) -> dict:
        return await self._request("GET", "/v1/deployment_runs", params=self._clean_params(params))

    # ---------- Channels（独立基址 forward/v0） ----------

    async def create_channel(self, payload: dict) -> dict:
        return await self._request("POST", "/channels", json_body=payload, base=self.channel_base, retry=False)

    async def list_channels(self, params: dict | None = None) -> dict:
        return await self._request("GET", "/channels", params=self._clean_params(params), base=self.channel_base)

    async def get_channel(self, channel_id: str) -> dict:
        return await self._request("GET", f"/channels/{channel_id}", base=self.channel_base)

    async def patch_channel(self, channel_id: str, payload: dict) -> dict:
        return await self._request(
            "PATCH", f"/channels/{channel_id}", json_body=payload, base=self.channel_base, retry=False
        )

    async def delete_channel(self, channel_id: str) -> dict:
        return await self._request("DELETE", f"/channels/{channel_id}", base=self.channel_base)

    async def create_wechat_qr_session(self, channel_id: str) -> dict:
        return await self._request(
            "POST", f"/channels/{channel_id}/qr-sessions", json_body={}, base=self.channel_base, retry=False
        )

    async def get_wechat_qr_session(self, channel_id: str, session_key: str) -> dict:
        return await self._request(
            "GET", f"/channels/{channel_id}/qr-sessions/{session_key}", base=self.channel_base
        )

    # ---------- Vaults ----------

    async def create_vault(self, payload: dict) -> dict:
        return await self._request("POST", "/v1/vaults", json_body=payload)

    async def list_vaults(self, params: dict | None = None) -> dict:
        return await self._request("GET", "/v1/vaults", params=self._clean_params(params))

    async def get_vault(self, vault_id: str) -> dict:
        return await self._request("GET", f"/v1/vaults/{vault_id}")

    async def update_vault(self, vault_id: str, payload: dict) -> dict:
        return await self._request("POST", f"/v1/vaults/{vault_id}", json_body=payload)

    async def archive_vault(self, vault_id: str) -> dict:
        return await self._request("POST", f"/v1/vaults/{vault_id}/archive", json_body={})

    async def delete_vault(self, vault_id: str) -> dict:
        return await self._request("DELETE", f"/v1/vaults/{vault_id}")

    async def add_credential(self, vault_id: str, payload: dict) -> dict:
        return await self._request(f"POST", f"/v1/vaults/{vault_id}/credentials", json_body=payload, retry=False)

    async def list_credentials(self, vault_id: str, params: dict | None = None) -> dict:
        return await self._request("GET", f"/v1/vaults/{vault_id}/credentials", params=self._clean_params(params))

    async def get_credential(self, vault_id: str, credential_id: str) -> dict:
        return await self._request("GET", f"/v1/vaults/{vault_id}/credentials/{credential_id}")

    async def update_credential(self, vault_id: str, credential_id: str, payload: dict) -> dict:
        return await self._request(
            "POST", f"/v1/vaults/{vault_id}/credentials/{credential_id}", json_body=payload, retry=False
        )

    async def archive_credential(self, vault_id: str, credential_id: str) -> dict:
        return await self._request(
            "POST", f"/v1/vaults/{vault_id}/credentials/{credential_id}/archive", json_body={}
        )

    async def delete_credential(self, vault_id: str, credential_id: str) -> dict:
        return await self._request("DELETE", f"/v1/vaults/{vault_id}/credentials/{credential_id}")
