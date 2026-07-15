# danmaku_queue.py — BiliDanmaku 弹幕缓冲队列
# 线程安全的弹幕缓冲队列，基于墙上时钟时间发射弹幕。
#
# 设计原则:
#   - 弹幕按 video_time 排序存储，tick(elapsed) 返回当前应发射的弹幕。
#   - 每条弹幕仅发射一次（基于索引指针递增，非 ID 去重）。
#   - 最大容量限制（默认 2000 条），超出截断保留最早的弹幕。
#   - 线程安全: 所有公开方法使用 threading.Lock 保护内部状态。
#   - 零业务依赖: 不依赖 PyQt / events / data_dispatcher / main_window。
#
# 墙上时钟 vs 视频进度:
#   v0.2 使用墙上时钟 (time.monotonic() 差值) 作为 elapsed 参数。
#   弹幕发射节奏仅取决于本地时钟，不与视频播放器进度同步。
#   v0.3+ 将新增进度同步模式 (seek 感知 + 弹幕重新调度)。
#
# v0.3+ 将扩展:
#   - 进度同步模式（基于 video progress 而非 wall clock）
#   - 弹幕过滤（按 mode / pool / font_size）
#   - 弹幕密度控制
#
# 用法:
#   queue = DanmakuQueue(max_capacity=2000)
#   queue.load(danmaku_items)          # 视频切换时加载新弹幕
#
#   start_time = time.monotonic()
#   while True:
#       elapsed = time.monotonic() - start_time
#       new_items = queue.tick(elapsed)  # 当前帧应发射的弹幕
#       for item in new_items:
#           render(item)
#
# 依赖: Python 3.8+ 标准库 (threading), danmaku_parser (DanmakuItem)

from __future__ import annotations

import threading
from typing import List

# DanmakuItem 是纯数据类，仅用于类型标注和排序键。
# 队列不依赖 danmaku_parser 的任何解析逻辑。
from danmaku_parser import DanmakuItem


class DanmakuQueue:
    """弹幕缓冲队列。

    按弹幕时间排序存储，基于墙上时钟时间 (elapsed) 发射弹幕。
    每条弹幕仅发射一次，视频切换时自动清空旧弹幕。

    线程安全: 所有公开方法使用 threading.Lock 保护内部状态。
    调用方可在任意线程调用 tick() / load() / clear()。

    属性:
        capacity: 最大容量（构造时设定，只读）。
        total: 队列中弹幕总数（含已发射）。
        remaining: 尚未发射的弹幕数量。
        emitted_count: 已发射的弹幕数量。
    """

    # 默认最大容量
    DEFAULT_CAPACITY = 2000

    def __init__(self, max_capacity: int = DEFAULT_CAPACITY) -> None:
        """初始化弹幕队列。

        Args:
            max_capacity: 最大弹幕容量。加载时若 items 超过此值，
                          截断保留最早的 max_capacity 条。

        Raises:
            ValueError: max_capacity < 1。
        """
        if max_capacity < 1:
            raise ValueError(
                f'max_capacity 必须 >= 1, 实际: {max_capacity}'
            )

        self._max_capacity = max_capacity
        self._items: List[DanmakuItem] = []
        self._next_index: int = 0
        self._lock = threading.Lock()

    # ── 公开接口 ───────────────────────────────────────────────

    def load(self, items: List[DanmakuItem]) -> None:
        """加载弹幕列表。

        清空旧弹幕，按 video_time 升序排列后存入队列。
        若 items 数量超过 max_capacity，截断保留前 max_capacity 条
        （即 video_time 最早的弹幕）。

        此方法隐含 clear() — 适用于视频切换场景。

        Args:
            items: DanmakuItem 列表（通常来自 danmaku_parser）。
                   可以为空列表（清空队列）。
        """
        with self._lock:
            # 按弹幕出现时间升序排列
            sorted_items = sorted(items, key=lambda x: x.time)

            # 容量限制: 保留最早的 max_capacity 条
            if len(sorted_items) > self._max_capacity:
                sorted_items = sorted_items[:self._max_capacity]

            self._items = sorted_items
            self._next_index = 0

    def tick(self, elapsed: float) -> List[DanmakuItem]:
        """返回当前 elapsed 时刻应发射的弹幕。

        收集所有满足 time <= elapsed 且尚未发射过的弹幕，
        按 video_time 升序返回。每条弹幕仅在其第一次满足条件时返回。

        复杂度: O(k) 其中 k 为本帧新发射的弹幕数量。
        已发射的弹幕通过索引指针跳过，不重复扫描。

        Args:
            elapsed: 自视频开始播放以来的墙上时钟时间（秒）。
                     通常由调用方通过 time.monotonic() - start_time 计算。

        Returns:
            本帧应发射的弹幕列表（按 time 升序）。
            无新弹幕时返回空列表。
            返回值为内部列表的浅拷贝，外部修改不影响队列状态。
        """
        with self._lock:
            if not self._items:
                return []

            # 从 _next_index 开始扫描，收集所有 time <= elapsed 的弹幕
            start = self._next_index
            end = start

            for i in range(start, len(self._items)):
                if self._items[i].time <= elapsed:
                    end = i + 1
                else:
                    # 弹幕按 time 排序，后续的 time 更大，提前终止
                    break

            if end == start:
                return []

            result = self._items[start:end]
            self._next_index = end
            return list(result)

    def clear(self) -> None:
        """清空所有弹幕并重置发射状态。

        适用于视频停止播放、连接断开等场景。
        """
        with self._lock:
            self._items.clear()
            self._next_index = 0

    # ── 属性 (只读) ────────────────────────────────────────────

    @property
    def remaining(self) -> int:
        """尚未发射的弹幕数量。"""
        with self._lock:
            return len(self._items) - self._next_index

    @property
    def total(self) -> int:
        """队列中弹幕总数（含已发射的）。"""
        with self._lock:
            return len(self._items)

    @property
    def capacity(self) -> int:
        """最大容量（构造时设定，只读）。"""
        return self._max_capacity

    @property
    def emitted_count(self) -> int:
        """已发射的弹幕数量。"""
        with self._lock:
            return self._next_index
