# events.py — BiliDanmaku 内部事件定义
# 定义所有跨模块通信的事件类型及其携带的数据结构。
#
# 职责边界:
#   - 纯数据定义，无业务逻辑
#   - 不依赖 PyQt、不依赖 dispatcher
#   - 事件数据类使用 @dataclass，方便序列化和日志打印
#
# 依赖: Python 3.8+ 标准库 (dataclasses, enum)

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from danmaku_parser import DanmakuParseResult


class EventType(Enum):
    """内部事件类型枚举。

    每个事件类型对应一个数据类，消费者根据 type 决定如何处理 payload。
    """
    VIDEO_SWITCHED = auto()   # 浏览器检测到视频切换 (payload: VideoSwitchedEvent)
    DANMAKU_LOADED = auto()   # 弹幕获取+解析完成 (payload: DanmakuLoadedEvent)
    PROGRESS_UPDATED = auto() # 浏览器上报播放进度 (payload: ProgressUpdatedEvent)


# ── Event Data Classes ──────────────────────────────────────────────


@dataclass
class VideoSwitchedEvent:
    """视频切换事件 — 浏览器检测到用户打开或切换了 B站视频。

    对应 extension/background.js 发送的 video_switch 消息。
    """
    bv: str
    cid: int | None = None    # FULL Resolver 提供；PARTIAL 时为 None
    title: str = ''
    duration: float | None = None
    resolver_level: str = 'UNKNOWN'  # "FULL" | "PARTIAL" | "UNKNOWN"
    cookie: str | None = None        # 浏览器 B站 cookie 字符串


@dataclass
class DanmakuLoadedEvent:
    """弹幕加载完成事件 — danmaku_handler 编排流程成功/失败后的结果。

    消费方:
        - stderr 日志输出 (打印 summary)
        - danmaku_queue (载入 items 供渲染)
        - native_host (回复 status 给浏览器)
    """
    bv: str
    cid: int
    title: str = ''
    success: bool = False
    items: List = field(default_factory=list)    # List[DanmakuItem]
    total: int = 0
    error: str | None = None
    summary: str = ''                            # 人类可读摘要


@dataclass
class ProgressUpdatedEvent:
    """播放进度更新事件 — 浏览器每秒上报。

    对应 extension/background.js 发送的 progress_update 消息。
    v0.2 阶段由 danmaku_queue 消费（播放同步预留）；v0.2 使用墙上时钟方式。
    """
    bv: str
    progress: float           # currentTime (秒)
    is_playing: bool = False
