"""极简 HTTP 客户端。

只用标准库，避免 CI 里装依赖失败导致整条流水线挂掉。
关键设计：交易所的 4xx 通常携带业务错误码（如币安 -2015 权限不足），
这里把它当作「正常返回」交给上层判断，而不是抛异常。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

USER_AGENT = "FIRE-Progress/1.0 (+https://github.com/SayangChun/FIRE-Progress)"


def request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 20,
    retries: int = 3,
    backoff: float = 1.5,
) -> dict:
    """发起请求并返回解析后的 JSON。

    5xx / 网络错误会重试；4xx 直接返回错误体供上层识别业务错误码。
    """
    last_error: Exception | None = None

    for attempt in range(retries):
        req = urllib.request.Request(url, method=method, data=body)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/json")
        for key, value in (headers or {}).items():
            req.add_header(key, value)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read().decode("utf-8", "replace")
                payload = json.loads(raw) if raw.strip() else {}
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {"data": payload}
            payload["_http_status"] = exc.code
            if exc.code < 500:
                return payload  # 业务错误，不重试
            last_error = exc
        except Exception as exc:  # 超时、DNS、连接重置等
            last_error = exc

        if attempt < retries - 1:
            time.sleep(backoff**attempt)

    raise RuntimeError(f"请求失败 {url} -> {last_error}") from last_error


def fetch_json(url: str, **kwargs) -> dict:
    return request(url, **kwargs)


def fetch_text(
    url: str,
    *,
    timeout: int = 20,
    retries: int = 3,
    backoff: float = 1.5,
) -> str:
    """抓取纯文本（如 CSV）。与 request 不同，这里不解析 JSON。"""
    last_error: Exception | None = None

    for attempt in range(retries):
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "text/plain, text/csv, */*")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8-sig", "replace")
        except Exception as exc:
            last_error = exc

        if attempt < retries - 1:
            time.sleep(backoff**attempt)

    raise RuntimeError(f"请求失败 {url} -> {last_error}") from last_error
