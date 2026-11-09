"""统一业务错误。API 层转 JSON 信封：{"code", "message", "detail"}。"""
from typing import Any


class PlatformError(Exception):
    def __init__(self, status_code: int, code: str, message: str, detail: Any = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)


def bad_request(message: str, code: str = "invalid_request", detail: Any = None) -> PlatformError:
    return PlatformError(400, code, message, detail)


def not_found(message: str = "资源不存在", code: str = "not_found") -> PlatformError:
    return PlatformError(404, code, message)


def insufficient_balance(message: str = "余额不足，请充值后重试") -> PlatformError:
    return PlatformError(402, "insufficient_balance", message)


def upstream_error(status_code: int, code: str, message: str, detail: Any = None) -> PlatformError:
    return PlatformError(status_code if status_code >= 400 else 502, f"upstream_{code}", message, detail)
