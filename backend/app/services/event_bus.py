"""RunEvent Redis pub/sub 总线(Step 2.4)。

写入侧:append_event 持久化成功后调用 publish_event,把事件 JSON
发布到 per-run channel `run_events:{run_id}`。同步 Redis 客户端,
运行在 worker/API 进程;发布失败仅记日志,不抛错——订阅端有周期性
DB 兜底,不会丢事件。

订阅侧:EventService.stream 通过 open_subscription 订阅 channel
获得毫秒级推送;Redis 不可用时抛异常,由调用方回退 DB 轮询。
"""

import json
import logging
import threading
from typing import Any

import redis.asyncio as aioredis
from redis import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# 终态事件类型:订阅端收到后即可结束该 run 的流
TERMINAL_EVENT_TYPES = {"run_completed", "run_failed", "run_cancelled"}


def channel_name(run_id: str) -> str:
    return f"run_events:{run_id}"


def event_to_dict(event: Any) -> dict:
    """ORM RunEvent -> 可 JSON 序列化 dict(与 RunEventOut 字段对齐)。"""
    from app.schemas.run import RunEventOut

    return RunEventOut.model_validate(event).model_dump(mode="json")


# ---- 发布(同步,worker/API 进程) ----

_publisher: Redis | None = None
_publisher_lock = threading.Lock()


def _get_publisher() -> Redis:
    """惰性初始化发布连接,进程内复用(redis-py 自带连接池,线程安全)。"""
    global _publisher
    with _publisher_lock:
        if _publisher is None:
            _publisher = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return _publisher


def publish_event(event: Any) -> None:
    """发布事件到 per-run channel。事件需已 commit 成功后再发布。

    任何失败都静默降级(记日志):订阅端的周期性查库兜底保证不丢事件。
    """
    try:
        data = event_to_dict(event)
    except Exception:
        logger.warning("serialize event failed, skip publish", exc_info=True)
        return
    run_id = data.get("run_id")
    if not run_id:
        return
    try:
        _get_publisher().publish(
            channel_name(run_id), json.dumps(data, ensure_ascii=False)
        )
    except Exception:
        logger.warning(
            "publish event(run=%s seq=%s) failed; subscribers will backfill from DB",
            run_id,
            data.get("sequence"),
            exc_info=True,
        )


# ---- 订阅(asyncio,API 进程 SSE 连接) ----


async def open_subscription(run_id: str):
    """订阅 run 的事件 channel;Redis 不可用时抛异常,由调用方回退轮询。

    await pubsub.subscribe() 返回即代表订阅确认已收到,此后该 channel
    的 publish 均会推送到本订阅(subscribe-then-poll 模式的前提)。
    """
    client = aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(channel_name(run_id))
    except Exception:
        await _aclose(pubsub)
        await _aclose(client)
        raise
    # 把 client 挂在 pubsub 上,close_subscription 时一并释放
    pubsub._ma_client = client  # type: ignore[attr-defined]
    return pubsub


async def close_subscription(pubsub) -> None:
    client = getattr(pubsub, "_ma_client", None)
    await _aclose(pubsub)
    if client is not None:
        await _aclose(client)


async def _aclose(resource) -> None:
    """兼容 redis-py 4.x(close)/5.x+(aclose)的关闭助手。"""
    closer = getattr(resource, "aclose", None) or getattr(resource, "close", None)
    if closer is not None:
        result = closer()
        if hasattr(result, "__await__"):
            await result
