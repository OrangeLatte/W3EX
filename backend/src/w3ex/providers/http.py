"""真实数据源共享 HTTP 层：TTL 缓存 + 超时 + 指数退避重试。

所有真实 Provider 复用此模块，避免各自直连。失败统一抛 ProviderUnavailable。

评审工程项治理：
- TTLCache 容量上限（LRU 淘汰），防止无限膨胀
- single-flight：同 key 并发请求共享同一次上游调用
- stale-if-error：上游失败时回退过期缓存值，保证可用性优先
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import time
from collections import OrderedDict
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

import httpx

from w3ex.providers.base import ProviderUnavailable

_CLIENT: httpx.AsyncClient | None = None

DEFAULT_TIMEOUT = 5.0
DEFAULT_RETRIES = 1
DEFAULT_TTL = 10.0
CACHE_MAXSIZE = 512

_INFLIGHT: dict[str, asyncio.Future[Any]] = {}


def _detect_system_proxy() -> str | None:
    """探测代理：显式环境变量优先，macOS 下回退读取系统代理（scutil --proxy）。

    背景：macOS 的 curl 构建会自动走系统代理，而 httpx 只读环境变量——
    若系统配了本地代理（如 Clash 9674），直连会被 GFW SNI 封锁导致
    binance/coingecko 全部 ConnectTimeout，curl 却正常。此函数消除该差异。
    """
    for var in ("W3EX_HTTPS_PROXY", "https_proxy", "HTTPS_PROXY"):
        v = os.environ.get(var)
        if v:
            return v
    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["scutil", "--proxy"], capture_output=True, text=True, timeout=3
            ).stdout
            if re.search(r"HTTPSEnable\s*:\s*1", out):
                host = re.search(r"HTTPSProxy\s*:\s*(\S+)", out)
                port = re.search(r"HTTPSPort\s*:\s*(\d+)", out)
                if host and port:
                    return f"http://{host.group(1)}:{port.group(1)}"
        except Exception:  # noqa: BLE001 — 代理探测失败不影响直连回退
            return None
    return None


def _get_client() -> httpx.AsyncClient:
    global _CLIENT
    if _CLIENT is None or _CLIENT.is_closed:
        _CLIENT = httpx.AsyncClient(
            # connect 与 read 分离：经本地代理出网时，首次 CONNECT 隧道建立可达 7-8s，
            # 统一 5s 超时会把隧道预热误判为死源（连锁熔断→mock 回退）
            timeout=httpx.Timeout(connect=12.0, read=DEFAULT_TIMEOUT, write=5.0, pool=3.0),
            proxy=_detect_system_proxy(),
            # 显式限制：避免单个死源（长时间 connect 挂起）占满默认连接池，
            # 把健康源的请求一起拖死（评审发现的 vision 熔断误开根因之一）
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=8),
            headers={"User-Agent": "w3ex-mvp/0.1 (+market-data)"},
            follow_redirects=True,
        )
    return _CLIENT


async def get_client() -> httpx.AsyncClient:
    """异步上下文获取共享 client（LLM / 外部 API 复用同一代理与连接池配置）。"""
    return _get_client()


async def close_client() -> None:
    global _CLIENT
    if _CLIENT is not None and not _CLIENT.is_closed:
        await _CLIENT.aclose()
    _CLIENT = None


async def reset_client() -> None:
    """自愈：丢弃当前共享 httpx 客户端（keepalive 死连接/代理状态残留时调用）。

    下一次 get_client() 会按当前环境重建（含系统代理探测）。
    """
    await close_client()


class TTLCache:
    """进程内 TTL 缓存：LRU 容量上限 + allow_stale（stale-if-error 回退用）。"""

    def __init__(self, maxsize: int = CACHE_MAXSIZE) -> None:
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._maxsize = maxsize

    def __len__(self) -> int:
        return len(self._store)

    def get(self, key: str, *, allow_stale: bool = False) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        expires, value = item
        if time.monotonic() > expires and not allow_stale:
            # 过期视为 miss 但不删除——条目留给 stale-if-error 回退，容量由 LRU 上限兜底
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: float) -> None:
        self._store[key] = (time.monotonic() + ttl, value)
        self._store.move_to_end(key)
        while len(self._store) > self._maxsize:
            self._store.popitem(last=False)


_CACHE = TTLCache()


# ---------------------------------------------------------------------------
# 熔断器（circuit breaker）：持续失败的上游域名冷却期内快速失败，
# 避免死源（超时/挂起）每次请求都消耗完整超时预算并拖垮连接池。
# ---------------------------------------------------------------------------
_CIRCUIT_FAIL_THRESHOLD = 3
_CIRCUIT_COOLDOWN_S = 120.0
_CIRCUIT: dict[str, dict[str, float]] = {}


def _origin_of(url: str) -> str:
    return urlsplit(url).netloc


def _circuit_check(origin: str) -> None:
    if not origin:  # 相对/空 URL 无法归因域名，不纳入熔断
        return
    entry = _CIRCUIT.get(origin)
    if entry and monotonic() < entry.get("open_until", 0.0):
        raise ProviderUnavailable(f"circuit open for {origin}（冷却中，跳过上游请求）")


def _circuit_success(origin: str) -> None:
    _CIRCUIT.pop(origin, None)


def _circuit_failure(origin: str) -> None:
    entry = _CIRCUIT.setdefault(origin, {"fails": 0.0})
    entry["fails"] = entry.get("fails", 0.0) + 1
    if entry["fails"] >= _CIRCUIT_FAIL_THRESHOLD:
        entry["open_until"] = monotonic() + _CIRCUIT_COOLDOWN_S


def reset_circuit() -> None:
    """测试与运维用：清空全部熔断状态。"""
    _CIRCUIT.clear()


async def _do_fetch(
    url: str,
    *,
    method: str,
    params: dict[str, Any] | None,
    json_body: Any,
    headers: dict[str, str] | None,
    retries: int,
) -> Any:
    origin = _origin_of(url)
    _circuit_check(origin)
    backoff = 0.5
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            client = _get_client()
            resp = await client.request(method, url, params=params, json=json_body, headers=headers)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise ProviderUnavailable(f"upstream {url} -> {resp.status_code}")
            if resp.status_code >= 400:
                # 4xx 属于请求本身的问题（如不存在的交易对），不重试直接判不可用
                raise ProviderUnavailable(f"upstream {url} -> {resp.status_code}")
            _circuit_success(origin)
            return resp.json()
        except (httpx.HTTPError, ProviderUnavailable, ValueError) as exc:
            last_error = exc
            if attempt < retries and method == "GET":
                await asyncio.sleep(backoff)
                backoff *= 2
    _circuit_failure(origin)
    raise ProviderUnavailable(f"upstream {url} 不可达: {last_error!r}") from last_error


async def fetch_json(
    url: str,
    *,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    json_body: Any = None,
    headers: dict[str, str] | None = None,
    ttl: float = DEFAULT_TTL,
    retries: int = DEFAULT_RETRIES,
    cache_key: str | None = None,
    cacheable: bool = True,
) -> Any:
    """请求 JSON 并缓存；同 key 并发共享单次请求（single-flight）。

    上游失败时：若存在过期缓存值则回退（stale-if-error），否则抛 ProviderUnavailable。
    """
    key = cache_key or f"{method}:{url}:{params}:{json_body}"
    if cacheable:
        cached = _CACHE.get(key)
        if cached is not None:
            return cached
        inflight = _INFLIGHT.get(key)
        if inflight is not None:
            return await asyncio.shield(inflight)

    if cacheable:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        _INFLIGHT[key] = fut
        try:
            data = await _do_fetch(
                url,
                method=method,
                params=params,
                json_body=json_body,
                headers=headers,
                retries=retries,
            )
        except BaseException as exc:
            fut.set_exception(exc)
            _INFLIGHT.pop(key, None)
            if cacheable:
                stale = _CACHE.get(key, allow_stale=True)
                if stale is not None:
                    return stale
            raise
        fut.set_result(data)
        _INFLIGHT.pop(key, None)
        _CACHE.set(key, data, ttl)
        return data

    return await _do_fetch(
        url, method=method, params=params, json_body=json_body, headers=headers, retries=retries
    )


def cache_snapshot_size() -> int:
    return len(_CACHE)
