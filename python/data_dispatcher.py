# data_dispatcher.py — 线程安全内部事件总线
# 为各 Python 模块提供发布-订阅消息机制，解耦生产者与消费者。
#
# 设计原则:
#   - 同步分发: 订阅者回调在发布者线程中执行（v0.2 简化方案）。
#     订阅者回调应快速返回（如将数据推入自己的内部队列）。
#     耗时操作（HTTP 请求等）不应在回调中执行。
#   - 线程安全: 订阅者注册表使用 threading.Lock 保护。
#   - 零依赖: 不引入 PyQt 或第三方库，纯 Python 标准库。
#
# 用法:
#   dispatcher = DataDispatcher()
#   dispatcher.subscribe(EventType.DANMAKU_LOADED, my_handler)
#   dispatcher.publish(DanmakuLoadedEvent(...))
#
# 依赖: Python 3.8+ 标准库 (threading, typing)

from __future__ import annotations

import threading
from typing import Callable, Dict, List

from events import EventType


# 回调签名: Callable[[object], None] — 接收一个事件数据类实例
Subscriber = Callable[[object], None]


class DataDispatcher:
    """线程安全的事件发布-订阅总线。

    内部维护一个 {EventType → [callback, ...]} 的注册表。
    publish() 时同步调用所有注册的回调，回调在发布者线程中执行。
    """

    def __init__(self) -> None:
        self._subscribers: Dict[EventType, List[Subscriber]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: EventType, callback: Subscriber) -> None:
        """订阅指定事件类型。

        Args:
            event_type: 事件类型枚举值。
            callback: 事件发生时调用的函数，签名为 callback(event) -> None。

        Raises:
            TypeError: event_type 不是 EventType 枚举。
        """
        if not isinstance(event_type, EventType):
            raise TypeError(
                f'event_type 必须是 EventType 枚举值, 实际: {type(event_type)}'
            )

        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: EventType, callback: Subscriber) -> bool:
        """取消订阅指定事件类型。

        Args:
            event_type: 事件类型枚举值。
            callback: 之前注册的回调函数。

        Returns:
            True 如果成功取消订阅，False 如果未找到该回调。
        """
        with self._lock:
            callbacks = self._subscribers.get(event_type, [])
            if callback in callbacks:
                callbacks.remove(callback)
                return True
            return False

    def publish(self, event: object) -> None:
        """发布事件到所有订阅者。

        同步调用：订阅者回调在发布者线程中执行。
        回调抛出的异常会被静默捕获（不传播），避免单个订阅者故障影响其他订阅者。

        Args:
            event: 事件数据类实例（如 DanmakuLoadedEvent, ProgressUpdatedEvent 等）。

        Raises:
            TypeError: 事件类型未注册（无 EventType 属性）。
        """
        event_type = self._event_type(event)

        with self._lock:
            callbacks = list(self._subscribers.get(event_type, []))

        for callback in callbacks:
            try:
                callback(event)
            except Exception:
                # 静默捕获: 单个订阅者崩溃不影响其他订阅者
                # v0.2 阶段异常信息通过 print 输出（v0.3+ 切换到 logging）
                import sys
                print(
                    f'[BiliDanmaku] DataDispatcher: 订阅者 {callback.__name__} '
                    f'处理事件 {event_type.name} 时异常',
                    file=sys.stderr,
                )

    def subscriber_count(self, event_type: EventType | None = None) -> int:
        """查询订阅者数量。

        Args:
            event_type: 事件类型。为 None 时返回所有类型的订阅者总数。

        Returns:
            订阅者数量。
        """
        with self._lock:
            if event_type is None:
                return sum(len(v) for v in self._subscribers.values())
            return len(self._subscribers.get(event_type, []))

    def reset(self) -> None:
        """清空所有订阅者（仅用于测试和进程重启场景）。"""
        with self._lock:
            self._subscribers.clear()

    # ── 内部辅助 ──────────────────────────────────────────────

    @staticmethod
    def _event_type(event: object) -> EventType:
        """从事件实例推断 EventType。

        约定: 事件数据类名 → EventType 枚举名:
            DanmakuLoadedEvent → DANMAKU_LOADED
            VideoSwitchedEvent → VIDEO_SWITCHED
            ProgressUpdatedEvent → PROGRESS_UPDATED

        映射规则: 去掉 "Event" 后缀，转换为 UPPER_SNAKE_CASE。
        """
        class_name = type(event).__name__
        if not class_name.endswith('Event'):
            raise TypeError(
                f'事件类名必须以 "Event" 结尾, 实际: {class_name}'
            )

        # DanmakuLoadedEvent → DanmakuLoaded → DANMAKU_LOADED
        base = class_name[:-5]  # 去掉 "Event" 后缀
        # 在大小写切换处插入下划线并大写
        snake = ''
        for i, ch in enumerate(base):
            if i > 0 and ch.isupper() and (base[i-1].islower() or
                   (i + 1 < len(base) and base[i+1].islower())):
                snake += '_'
            snake += ch.upper()
        event_name = snake

        try:
            return EventType[event_name]
        except KeyError:
            raise TypeError(
                f'无法从事件类名 "{class_name}" 推断 EventType。'
                f'推断的枚举名: {event_name}'
            ) from None


# ── 模块级单例 ───────────────────────────────────────────────────
# 提供默认的全局 dispatcher 实例。各模块可通过 "from data_dispatcher
# import dispatcher" 获取同一个实例，无需手动传递引用。
#
# 测试代码应创建独立的 DataDispatcher() 实例以保持隔离。

dispatcher = DataDispatcher()
