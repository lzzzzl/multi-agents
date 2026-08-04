"""RQ 队列配置。

启动 worker:
    uv run rq worker runs
"""

from redis import Redis
from rq import Queue

from app.core.config import settings

_redis = Redis.from_url(settings.REDIS_URL, decode_responses=False)
runs_queue = Queue("runs", connection=_redis)


def get_queue() -> Queue:
    return runs_queue
