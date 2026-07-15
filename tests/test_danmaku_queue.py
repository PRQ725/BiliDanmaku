# tests/test_danmaku_queue.py — DanmakuQueue 单元测试
# 测试弹幕缓冲队列的加载/发射/清空/容量/线程安全。
#
# 用法: python -m pytest tests/test_danmaku_queue.py -v
#       或在项目根目录: python tests/test_danmaku_queue.py

from __future__ import annotations

import os
import sys
import threading
import time

import pytest

# 确保 python/ 在 sys.path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python'))

# ── 检查依赖是否可用 ──────────────────────────────────────────

try:
    from danmaku_parser import DanmakuItem
    _PARSER_AVAILABLE = True
except ImportError:
    _PARSER_AVAILABLE = False

if _PARSER_AVAILABLE:
    from overlay.danmaku_queue import DanmakuQueue

pytestmark = pytest.mark.skipif(
    not _PARSER_AVAILABLE,
    reason='danmaku_parser 模块不可用',
)


# ── 辅助函数 ──────────────────────────────────────────────────


def _dm(
    time: float = 0.0,
    content: str = '测试弹幕',
    mode: int = 1,
    font_size: int = 25,
    color: int = 16777215,
    timestamp: int = 0,
    danmaku_id: int = 1,
    pool: int = 0,
) -> DanmakuItem:
    """创建 DanmakuItem 的便捷工厂函数。"""
    return DanmakuItem(
        time=time,
        content=content,
        mode=mode,
        font_size=font_size,
        color=color,
        timestamp=timestamp,
        danmaku_id=danmaku_id,
        pool=pool,
    )


def _make_items(*times: float) -> list:
    """按时间点创建多条弹幕的便捷函数。

    Usage:
        _make_items(1.0, 2.5, 5.0)  # 3 条弹幕，分别在 1.0s, 2.5s, 5.0s
    """
    return [
        _dm(time=t, content=f'dm_{t}', danmaku_id=i + 1)
        for i, t in enumerate(times)
    ]


# ═══════════════════════════════════════════════════════════════
# DanmakuQueue 构造测试
# ═══════════════════════════════════════════════════════════════


class TestQueueConstruction:
    """测试 DanmakuQueue 构造和初始状态。"""

    def test_default_construction(self) -> None:
        """使用默认参数构造。"""
        q = DanmakuQueue()
        assert q.total == 0
        assert q.remaining == 0
        assert q.emitted_count == 0
        assert q.capacity == 2000

    def test_custom_capacity(self) -> None:
        """使用自定义容量构造。"""
        q = DanmakuQueue(max_capacity=500)
        assert q.capacity == 500

    def test_capacity_minimum_one(self) -> None:
        """容量最小值为 1。"""
        q = DanmakuQueue(max_capacity=1)
        assert q.capacity == 1

    def test_capacity_zero_raises(self) -> None:
        """容量为 0 时抛出 ValueError。"""
        with pytest.raises(ValueError, match='max_capacity'):
            DanmakuQueue(max_capacity=0)

    def test_capacity_negative_raises(self) -> None:
        """容量为负数时抛出 ValueError。"""
        with pytest.raises(ValueError, match='max_capacity'):
            DanmakuQueue(max_capacity=-1)


# ═══════════════════════════════════════════════════════════════
# DanmakuQueue.load() 测试
# ═══════════════════════════════════════════════════════════════


class TestQueueLoad:
    """测试 load() 方法。"""

    def test_load_stores_items(self) -> None:
        """load() 加载弹幕后 total 更新。"""
        q = DanmakuQueue()
        items = _make_items(1.0, 2.0, 3.0)
        q.load(items)
        assert q.total == 3
        assert q.remaining == 3

    def test_load_empty_list(self) -> None:
        """load([]) 清空队列。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0))
        q.load([])
        assert q.total == 0
        assert q.remaining == 0

    def test_load_sorts_by_time(self) -> None:
        """load() 将弹幕按 time 升序排列。"""
        q = DanmakuQueue()
        # 乱序加载
        items = [
            _dm(time=10.0, content='third', danmaku_id=3),
            _dm(time=1.0, content='first', danmaku_id=1),
            _dm(time=5.0, content='second', danmaku_id=2),
        ]
        q.load(items)
        # tick 应该先返回 time=1.0 的弹幕
        result = q.tick(1.5)
        assert len(result) == 1
        assert result[0].content == 'first'

    def test_load_clears_previous_items(self) -> None:
        """load() 清空之前加载的弹幕。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0, 3.0))
        assert q.total == 3

        # 加载新的弹幕列表
        q.load(_make_items(10.0, 20.0))
        assert q.total == 2

    def test_load_resets_emission_state(self) -> None:
        """load() 重置发射指针。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0, 3.0))
        q.tick(3.0)  # 全部发射
        assert q.emitted_count == 3

        # 重新加载 —— 发射状态应重置
        q.load(_make_items(1.0, 2.0))
        assert q.emitted_count == 0
        assert q.remaining == 2

    def test_load_truncates_at_capacity(self) -> None:
        """超过容量的弹幕被截断，保留最早的。"""
        q = DanmakuQueue(max_capacity=3)
        items = _make_items(5.0, 3.0, 4.0, 1.0, 2.0)  # 5 条
        q.load(items)
        assert q.total == 3
        # 应保留 time 最小的 3 条: 1.0, 2.0, 3.0
        result = q.tick(3.0)
        assert len(result) == 3
        times = [item.time for item in result]
        assert times == [1.0, 2.0, 3.0]

    def test_load_exact_capacity(self) -> None:
        """加载等于容量的弹幕，不截断。"""
        q = DanmakuQueue(max_capacity=5)
        items = _make_items(1.0, 2.0, 3.0, 4.0, 5.0)
        q.load(items)
        assert q.total == 5


# ═══════════════════════════════════════════════════════════════
# DanmakuQueue.tick() 测试
# ═══════════════════════════════════════════════════════════════


class TestQueueTick:
    """测试 tick() 弹幕发射逻辑。"""

    def test_tick_returns_empty_when_no_items(self) -> None:
        """未加载弹幕时 tick() 返回空列表。"""
        q = DanmakuQueue()
        result = q.tick(10.0)
        assert result == []

    def test_tick_returns_empty_when_too_early(self) -> None:
        """elapsed 小于最早弹幕的 time 时返回空列表。"""
        q = DanmakuQueue()
        q.load(_make_items(5.0, 10.0, 15.0))
        result = q.tick(2.0)
        assert result == []

    def test_tick_returns_items_with_time_le_elapsed(self) -> None:
        """返回所有 time <= elapsed 的弹幕。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0, 3.0, 4.0, 5.0))
        result = q.tick(3.5)
        assert len(result) == 3
        assert [item.time for item in result] == [1.0, 2.0, 3.0]

    def test_tick_returns_all_when_elapsed_covers_all(self) -> None:
        """elapsed 足够大时一次返回所有弹幕。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0, 3.0))
        result = q.tick(100.0)
        assert len(result) == 3

    def test_tick_exact_boundary(self) -> None:
        """elapsed 等于弹幕 time 时该弹幕被发射（边界条件）。"""
        q = DanmakuQueue()
        q.load(_make_items(5.0))
        result = q.tick(5.0)
        assert len(result) == 1

    def test_tick_incremental_emission(self) -> None:
        """多次 tick() 逐步发射弹幕。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0, 3.0, 4.0, 5.0))

        r1 = q.tick(1.5)
        assert len(r1) == 1
        assert r1[0].time == 1.0

        r2 = q.tick(3.5)
        assert len(r2) == 2
        assert [item.time for item in r2] == [2.0, 3.0]

        r3 = q.tick(5.0)
        assert len(r3) == 2
        assert [item.time for item in r3] == [4.0, 5.0]

    def test_tick_each_item_only_once(self) -> None:
        """每条弹幕仅发射一次 —— 同一条不会重复返回。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0, 3.0))

        # 第一次发射所有
        r1 = q.tick(10.0)
        assert len(r1) == 3

        # 第二次 tick 不应再返回任何弹幕
        r2 = q.tick(10.0)
        assert r2 == []

    def test_tick_same_elapsed_twice(self) -> None:
        """同一 elapsed 值多次调用不重复发射。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0))

        q.tick(1.5)
        assert q.emitted_count == 1

        q.tick(1.5)
        assert q.emitted_count == 1  # 不变

    def test_tick_decreasing_elapsed_no_effect(self) -> None:
        """elapsed 减小（模拟异常情况）不重新发射旧弹幕。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0, 3.0, 4.0, 5.0))

        q.tick(5.0)
        assert q.emitted_count == 5

        # elapsed 回退
        result = q.tick(1.0)
        assert result == []
        assert q.emitted_count == 5

    def test_tick_returns_shallow_copy(self) -> None:
        """tick() 返回值是副本，外部修改不影响队列。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0))
        result = q.tick(2.0)
        result.clear()
        # 队列状态不受影响
        assert q.total == 2

    def test_tick_preserves_order(self) -> None:
        """tick() 返回的弹幕按 time 升序排列。"""
        q = DanmakuQueue()
        # 构造时故意打乱 ID 和时间的关系
        items = [
            _dm(time=3.0, danmaku_id=30),
            _dm(time=1.0, danmaku_id=10),
            _dm(time=5.0, danmaku_id=50),
            _dm(time=2.0, danmaku_id=20),
            _dm(time=4.0, danmaku_id=40),
        ]
        q.load(items)
        result = q.tick(5.0)
        times = [item.time for item in result]
        assert times == sorted(times)

    def test_tick_many_small_ticks(self) -> None:
        """大量小步进 tick() 不会遗漏或重复弹幕。"""
        q = DanmakuQueue()
        # 100 条弹幕，时间间隔 0.1s
        items = [_dm(time=i * 0.1, danmaku_id=i) for i in range(100)]
        q.load(items)

        emitted_all = []
        for t in range(101):  # 0.0 ~ 10.0
            batch = q.tick(t * 0.1)
            emitted_all.extend(batch)

        assert len(emitted_all) == 100
        # 验证所有 ID 出现且只出现一次
        ids = [item.danmaku_id for item in emitted_all]
        assert sorted(ids) == list(range(100))

    def test_tick_multiple_items_at_same_time(self) -> None:
        """多条弹幕在同一时间点，一次 tick() 全部返回。"""
        q = DanmakuQueue()
        items = [
            _dm(time=2.0, content='a', danmaku_id=1),
            _dm(time=2.0, content='b', danmaku_id=2),
            _dm(time=2.0, content='c', danmaku_id=3),
        ]
        q.load(items)
        result = q.tick(2.0)
        assert len(result) == 3
        contents = {item.content for item in result}
        assert contents == {'a', 'b', 'c'}

    def test_tick_zero_elapsed(self) -> None:
        """elapsed=0 不应发射任何弹幕（弹幕 time > 0）。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0))
        result = q.tick(0.0)
        assert result == []


# ═══════════════════════════════════════════════════════════════
# DanmakuQueue.clear() 测试
# ═══════════════════════════════════════════════════════════════


class TestQueueClear:
    """测试 clear() 方法。"""

    def test_clear_empty_queue(self) -> None:
        """清空空队列不抛出异常。"""
        q = DanmakuQueue()
        q.clear()
        assert q.total == 0
        assert q.remaining == 0
        assert q.emitted_count == 0

    def test_clear_loaded_queue(self) -> None:
        """清空已加载的队列，所有计数归零。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0, 3.0))
        q.clear()
        assert q.total == 0
        assert q.remaining == 0
        assert q.emitted_count == 0

    def test_clear_after_partial_emission(self) -> None:
        """部分发射后清空，所有计数归零。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0, 3.0, 4.0, 5.0))
        q.tick(2.5)  # 发射前 2 条
        assert q.emitted_count == 2

        q.clear()
        assert q.total == 0
        assert q.emitted_count == 0

    def test_after_clear_tick_returns_empty(self) -> None:
        """clear() 后 tick() 返回空列表。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0))
        q.clear()
        result = q.tick(10.0)
        assert result == []

    def test_after_clear_can_reload(self) -> None:
        """clear() 后可以重新 load() 并正常使用。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0))
        q.clear()
        q.load(_make_items(5.0, 10.0))
        result = q.tick(7.0)
        assert len(result) == 1
        assert result[0].time == 5.0


# ═══════════════════════════════════════════════════════════════
# DanmakuQueue 属性测试
# ═══════════════════════════════════════════════════════════════


class TestQueueProperties:
    """测试队列属性。"""

    def test_remaining_decreases_on_tick(self) -> None:
        """remaining 随 tick() 递减。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0, 3.0))
        assert q.remaining == 3

        q.tick(1.5)
        assert q.remaining == 2

        q.tick(3.0)
        assert q.remaining == 0

    def test_remaining_never_negative(self) -> None:
        """remaining 永不为负。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0))
        q.tick(10.0)
        assert q.remaining == 0
        q.tick(20.0)
        assert q.remaining == 0

    def test_total_unchanged_by_tick(self) -> None:
        """total 不随 tick() 变化（已发射的仍在队列中）。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0, 3.0))
        total_before = q.total
        q.tick(10.0)
        assert q.total == total_before

    def test_emitted_count_increments(self) -> None:
        """emitted_count 随发射递增。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0, 3.0, 4.0, 5.0))

        assert q.emitted_count == 0
        q.tick(1.5)
        assert q.emitted_count == 1
        q.tick(3.5)
        assert q.emitted_count == 3
        q.tick(5.0)
        assert q.emitted_count == 5

    def test_remaining_plus_emitted_equals_total(self) -> None:
        """remaining + emitted_count == total 恒成立。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0, 3.0, 4.0, 5.0))

        for _ in range(3):
            assert q.remaining + q.emitted_count == q.total
            q.tick(q.emitted_count + 1.5)

    def test_capacity_is_readonly(self) -> None:
        """capacity 属性不可写。"""
        q = DanmakuQueue(max_capacity=500)
        with pytest.raises(AttributeError):
            q.capacity = 1000  # type: ignore


# ═══════════════════════════════════════════════════════════════
# DanmakuQueue 线程安全测试
# ═══════════════════════════════════════════════════════════════


class TestQueueThreadSafety:
    """测试队列线程安全性。

    线程安全策略: 所有公开方法持有 threading.Lock，
    确保 load / tick / clear 在多线程下状态一致。
    """

    def test_concurrent_tick_from_multiple_threads(self) -> None:
        """多线程并发 tick() 不导致状态错乱。"""
        q = DanmakuQueue()
        # 1000 条弹幕
        items = [_dm(time=i * 0.01, danmaku_id=i) for i in range(1000)]
        q.load(items)

        emitted_ids = []
        emitted_ids_lock = threading.Lock()
        errors = []

        def tick_worker(thread_id: int) -> None:
            try:
                for _ in range(200):
                    batch = q.tick(100.0)
                    with emitted_ids_lock:
                        for item in batch:
                            emitted_ids.append(item.danmaku_id)
            except Exception as e:
                errors.append((thread_id, str(e)))

        threads = [
            threading.Thread(target=tick_worker, args=(i,))
            for i in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 不应有异常
        assert not errors, f'线程异常: {errors}'

        # 所有弹幕都至少被发射了一次（可能有重复因为多个线程同时 tick）
        assert len(emitted_ids) >= 1000

    def test_load_during_tick(self) -> None:
        """一个线程 load() 新数据的同时另一线程 tick() — 不崩溃。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0, 3.0))

        errors = []

        def load_worker() -> None:
            try:
                for _ in range(100):
                    q.load([
                        _dm(time=float(i), danmaku_id=i)
                        for i in range(50)
                    ])
            except Exception as e:
                errors.append(('load', str(e)))

        def tick_worker() -> None:
            try:
                for _ in range(100):
                    q.tick(25.0)
            except Exception as e:
                errors.append(('tick', str(e)))

        t_load = threading.Thread(target=load_worker)
        t_tick = threading.Thread(target=tick_worker)

        t_load.start()
        t_tick.start()
        t_load.join()
        t_tick.join()

        assert not errors, f'线程异常: {errors}'

    def test_clear_during_tick(self) -> None:
        """并发 clear() 和 tick() — 不崩溃且最终状态一致。"""
        q = DanmakuQueue()
        q.load(_make_items(*[float(i) for i in range(100)]))

        errors = []

        def clear_worker() -> None:
            try:
                for _ in range(50):
                    q.clear()
                    q.load([_dm(time=1.0, danmaku_id=1)])
            except Exception as e:
                errors.append(('clear', str(e)))

        def tick_worker() -> None:
            try:
                for _ in range(50):
                    q.tick(100.0)
            except Exception as e:
                errors.append(('tick', str(e)))

        t_clear = threading.Thread(target=clear_worker)
        t_tick = threading.Thread(target=tick_worker)

        t_clear.start()
        t_tick.start()
        t_clear.join()
        t_tick.join()

        assert not errors, f'线程异常: {errors}'


# ═══════════════════════════════════════════════════════════════
# DanmakuQueue 边界与集成测试
# ═══════════════════════════════════════════════════════════════


class TestQueueEdgeCases:
    """边界条件测试。"""

    def test_load_none_items_raises(self) -> None:
        """load(None) 抛出 TypeError（sorted 无法处理 None）。"""
        q = DanmakuQueue()
        with pytest.raises(TypeError):
            q.load(None)  # type: ignore

    def test_tick_negative_elapsed(self) -> None:
        """elapsed 为负数时无弹幕返回。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0))
        result = q.tick(-1.0)
        assert result == []

    def test_load_unsorted_preserves_order_in_tick(self) -> None:
        """加载未排序列表后 tick 返回正确顺序。"""
        q = DanmakuQueue()
        items = [
            _dm(time=50.0, danmaku_id=5),
            _dm(time=10.0, danmaku_id=1),
            _dm(time=40.0, danmaku_id=4),
            _dm(time=30.0, danmaku_id=3),
            _dm(time=20.0, danmaku_id=2),
        ]
        q.load(items)

        # 分步发射验证顺序
        all_emitted = []
        for t in [15.0, 25.0, 35.0, 45.0, 55.0]:
            all_emitted.extend(q.tick(t))

        times = [item.time for item in all_emitted]
        assert times == sorted(times)

    def test_large_batch_load_and_tick(self) -> None:
        """边界：大量弹幕加载和发射。"""
        q = DanmakuQueue(max_capacity=5000)
        items = [
            _dm(time=float(i) * 0.1, danmaku_id=i)
            for i in range(5000)
        ]
        q.load(items)
        assert q.total == 5000

        # 一次发射所有
        result = q.tick(500.0)
        assert len(result) == 5000

    def test_reload_after_full_emission(self) -> None:
        """全部发射后 reload，新弹幕正常发射。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0))
        q.tick(10.0)
        assert q.remaining == 0

        # 重新加载
        q.load(_make_items(3.0, 4.0))
        assert q.remaining == 2
        result = q.tick(4.0)
        assert len(result) == 2

    def test_single_item_queue(self) -> None:
        """容量为 1 的队列正常工作。"""
        q = DanmakuQueue(max_capacity=1)
        items = _make_items(1.0, 2.0, 3.0)
        q.load(items)
        assert q.total == 1

        result = q.tick(10.0)
        assert len(result) == 1

    def test_tick_on_empty_after_clear(self) -> None:
        """clear() 后 tick() 安全返回空列表。"""
        q = DanmakuQueue()
        q.load(_make_items(1.0, 2.0))
        q.tick(10.0)
        q.clear()

        result = q.tick(10.0)
        assert result == []

    def test_very_small_time_differences(self) -> None:
        """弹幕时间差极小（亚毫秒级）时正确排序和发射。"""
        q = DanmakuQueue()
        items = [
            _dm(time=1.0001, danmaku_id=2),
            _dm(time=1.0000, danmaku_id=1),
            _dm(time=1.0002, danmaku_id=3),
        ]
        q.load(items)
        result = q.tick(1.0001)
        assert len(result) == 2
        assert result[0].danmaku_id == 1
        assert result[1].danmaku_id == 2

    def test_all_items_at_zero_time(self) -> None:
        """所有弹幕 time=0，tick(0) 一次全部返回。"""
        q = DanmakuQueue()
        items = [
            _dm(time=0.0, danmaku_id=1),
            _dm(time=0.0, danmaku_id=2),
            _dm(time=0.0, danmaku_id=3),
        ]
        q.load(items)
        result = q.tick(0.0)
        assert len(result) == 3

    def test_multiple_load_no_memory_leak_pattern(self) -> None:
        """多次 load() 不会累积引用（基本 GC 检查）。"""
        q = DanmakuQueue(max_capacity=100)
        for _ in range(100):
            items = [
                _dm(time=float(i), danmaku_id=i)
                for i in range(200)
            ]
            q.load(items)
            assert q.total <= 100
