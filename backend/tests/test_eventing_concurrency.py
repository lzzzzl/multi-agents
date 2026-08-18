"""Step 2.2 事件 sequence 并发安全测试(真实 SQLite 引擎,非 mock)。

覆盖:
- 多线程并发向同一 run 追加事件:全部成功,sequence 恰为 1..N 无重复无空洞;
- (run_id, sequence) 唯一约束:直接写入重复 sequence 被 DB 拒绝;
- 撞号重试:IntegrityError 后回滚重算 sequence 再写,最终成功;
- 不同 run 之间 sequence 互不影响(各自从 1 开始)。
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, event, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import Run, RunEvent, Task
from app.services.eventing import append_event

THREADS = 8
EVENTS_PER_THREAD = 25


def _make_engine(tmp_path):
    """文件型 SQLite + WAL,允许多线程各自持连接并发写。"""
    engine = create_engine(
        f"sqlite:///{tmp_path}/events.db",
        connect_args={"timeout": 60, "check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_wal(dbapi_conn, _):  # pragma: no cover - 连接钩子
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    Base.metadata.create_all(
        engine, tables=[Task.__table__, Run.__table__, RunEvent.__table__]
    )
    return engine


def _seed_run(engine, run_id: str) -> None:
    with Session(engine) as db:
        db.add(Task(id=f"task_{run_id}", title="并发测试", status="running"))
        db.add(Run(id=run_id, task_id=f"task_{run_id}", status="running"))
        db.commit()


def test_concurrent_appends_have_unique_contiguous_sequences(tmp_path) -> None:
    """N 线程并发 append:全部写入成功,sequence 恰为 1..N*M。"""
    engine = _make_engine(tmp_path)
    _seed_run(engine, "run_cc")

    def worker(i: int) -> None:
        with Session(engine) as db:
            for j in range(EVENTS_PER_THREAD):
                append_event(
                    db,
                    "run_cc",
                    type="progress",
                    payload={"thread": i, "n": j},
                )

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        list(pool.map(worker, range(THREADS)))

    with Session(engine) as db:
        seqs = list(
            db.scalars(
                select(RunEvent.sequence)
                .where(RunEvent.run_id == "run_cc")
                .order_by(RunEvent.sequence.asc())
            )
        )

    total = THREADS * EVENTS_PER_THREAD
    assert len(seqs) == total
    assert seqs == list(range(1, total + 1))  # 无重复、无空洞、单调


def test_unique_constraint_rejects_duplicate_sequence(tmp_path) -> None:
    """绕过 append_event 直接插入重复 (run_id, sequence) 会被唯一约束拒绝。"""
    engine = _make_engine(tmp_path)
    _seed_run(engine, "run_uq")

    with Session(engine) as db:
        db.execute(
            insert(RunEvent).values(
                id="evt_a", run_id="run_uq", type="x", sequence=1, payload={}
            )
        )
        db.commit()

        with pytest.raises(IntegrityError):
            db.execute(
                insert(RunEvent).values(
                    id="evt_b", run_id="run_uq", type="x", sequence=1, payload={}
                )
            )
            db.commit()


def test_append_event_retries_on_integrity_error(tmp_path, monkeypatch) -> None:
    """撞号后 append_event 应回滚并重算 sequence 重写,最终成功。"""
    engine = _make_engine(tmp_path)
    _seed_run(engine, "run_rt")

    import app.services.eventing as eventing

    real = eventing._append_event_once
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            # 模拟并发方抢先把 sequence=1 写入
            raise IntegrityError("INSERT ... run_events", {}, Exception("duplicate key"))
        return real(*args, **kwargs)

    monkeypatch.setattr(eventing, "_append_event_once", flaky)
    monkeypatch.setattr(eventing.time, "sleep", lambda _s: None)

    with Session(engine) as db:
        ev = append_event(db, "run_rt", type="x", payload={})

    assert calls["n"] == 2  # 第一次冲突,重试成功
    assert ev.sequence == 1


def test_sequences_are_per_run(tmp_path) -> None:
    """不同 run 的事件序号相互独立,各自从 1 开始。"""
    engine = _make_engine(tmp_path)
    _seed_run(engine, "run_p1")
    _seed_run(engine, "run_p2")

    with Session(engine) as db:
        e1 = append_event(db, "run_p1", type="a")
        s1a = e1.sequence
        e2 = append_event(db, "run_p2", type="a")
        s2 = e2.sequence
        e3 = append_event(db, "run_p1", type="b")
        s1b = e3.sequence

    assert (s1a, s1b) == (1, 2)
    assert s2 == 1
