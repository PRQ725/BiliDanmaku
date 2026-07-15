# danmaku_renderer.py — BiliDanmaku 弹幕渲染引擎
# 使用 QPainter 在透明窗口上绘制滚动弹幕。
#
# 设计原则:
#   - 纯渲染层: 接收 danmaku_queue.tick() 返回的新弹幕，管理活跃弹幕列表，
#     每帧更新位置、绘制、清理越界弹幕。
#   - 墙上时钟驱动: 使用 QTimer 定时刷新（~30fps），位置增量基于帧间时差。
#     不依赖播放进度 — 弹幕发射节奏由 queue 的 wall-clock 时间轴控制。
#   - 多轨道管理: 新弹幕分配到第一个不重叠的空闲轨道，避免同轨道弹幕严重重叠。
#     v0.2 采用 first-fit 轨道分配，不做复杂碰撞优化。
#   - mode 过滤: v0.2 仅渲染滚动弹幕 (mode=1)。mode=4/5 数据保留但不渲染。
#   - 默认样式: 硬编码白色文字 + 黑色描边，25px Microsoft YaHei。
#     v0.3+ 将迁移到 config.py。
#   - 零业务依赖: 不依赖 events / data_dispatcher / native_host / main_window。
#   - 不修改 DanmakuItem 数据结构。
#
# 去重语义:
#   不做任何内容级去重。相同文本但不同 danmaku_id/timestamp 的弹幕
#   全部保留并发送给 renderer。B站大量重复弹幕是正常现象。
#   v0.2 不实现 deduplication。
#
# 用法:
#   app = QApplication(sys.argv)
#   renderer = DanmakuRenderer()
#   renderer.set_render_area(QRect(0, 0, 1920, 1080))
#   renderer.start()
#
#   # 每帧从 queue 拉取新弹幕:
#   new_items = queue.tick(elapsed)
#   renderer.enqueue(new_items)
#
#   # 绘制 (在 paintEvent 或回调中调用):
#   renderer.render(painter, rect)
#
# 依赖: PyQt6, danmaku_parser (DanmakuItem)

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Callable, Optional

from PyQt6.QtCore import QTimer, QRect, QPointF, pyqtSignal, QObject
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics, QPen

from danmaku_parser import DanmakuItem


# ── 活跃弹幕追踪结构 ────────────────────────────────────────────


@dataclass
class ActiveDanmaku:
    """追踪一条正在屏幕上滚动的弹幕。

    与 DanmakuItem 的关系:
        item — 原始弹幕数据（只读引用，不复制）
        x/y — 当前屏幕坐标 (x 为文字左边缘, y 为 baseline)
        width — 文字像素宽度（预计算，用于碰撞检测和越界判断）
        track — 分配的轨道编号
        speed — 滚动速度 (px/s)
    """
    item: DanmakuItem
    x: float
    y: float
    width: float
    track: int
    speed: float


# ── 渲染器 ──────────────────────────────────────────────────────


class DanmakuRenderer(QObject):
    """弹幕滚动渲染引擎。

    使用 QPainter.drawText() 在指定区域绘制滚动弹幕。
    QTimer 定时驱动帧更新（~30fps），位置计算基于帧间时差。

    渲染流程 (每帧):
        1. 外部调用 enqueue() 注入 queue.tick() 返回的新弹幕
        2. _on_frame() 更新所有活跃弹幕位置 (dx = speed * delta)
        3. 移除越界弹幕 (x + width < 0)
        4. 触发重绘 → render() 绘制所有活跃弹幕

    轨道管理:
        - 轨道高度 = font_size + padding
        - 新弹幕分配: first-fit — 第一个空闲轨道
        - 空闲判定: 同轨道最后一条弹幕已移过足够距离
        - v0.2 不实现复杂碰撞检测

    线程安全:
        所有公开方法应在同一线程（Qt GUI 线程）调用。
        v0.2 不实现跨线程渲染 — queue 的线程安全由 DanmakuQueue 保证，
        renderer 在 GUI 线程消费。

    属性:
        active_count: 当前活跃弹幕数量（只读）
        track_count: 当前轨道数量（只读）
        is_running: QTimer 是否正在运行（只读）
    """

    # ── 默认样式常量 (v0.2 硬编码, v0.3+ 迁移到 config.py) ──────

    DEFAULT_FONT_FAMILY = 'Microsoft YaHei'
    DEFAULT_FONT_SIZE = 25
    SCROLL_SPEED = 250          # 滚动速度 px/s
    TRACK_PADDING = 8           # 轨道间距 (px)
    TRACK_GAP = 80              # 同轨道相邻弹幕最小间距 (px)
    FRAME_INTERVAL = 33         # 帧间隔 ms (~30fps)
    TEXT_COLOR = QColor(255, 255, 255)
    OUTLINE_COLOR = QColor(0, 0, 0)

    # ── 信号 ────────────────────────────────────────────────────

    frame_rendered = pyqtSignal()
    """每帧渲染完成后发射。可供外部监听帧率统计。"""

    # ── 构造 ────────────────────────────────────────────────────

    def __init__(self, parent: Optional[QObject] = None) -> None:
        """初始化弹幕渲染器。

        Args:
            parent: 父 QObject。可传入 TransparentOverlay 以便访问其
                    update() 方法触发重绘。
        """
        super().__init__(parent)

        # ── 活跃弹幕 ──────────────────────────────────────────
        self._active: List[ActiveDanmaku] = []
        # 轨道列表: _tracks[i] = 轨道 i 上的活跃弹幕列表
        self._tracks: List[List[ActiveDanmaku]] = []

        # ── 渲染区域 ──────────────────────────────────────────
        self._render_area = QRect(0, 0, 1920, 1080)
        self._max_tracks = self._calc_max_tracks()

        # ── 字体 ──────────────────────────────────────────────
        self._font = QFont(self.DEFAULT_FONT_FAMILY, self.DEFAULT_FONT_SIZE)
        self._font_metrics: Optional[QFontMetrics] = None
        # 延迟创建 QFontMetrics（避免 QApplication 创建前访问）

        # ── 帧驱动 ────────────────────────────────────────────
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_frame)
        self._last_frame_time: float = 0.0
        self._running: bool = False

        # ── 文字宽度测量函数 (可注入, 便于测试) ────────────────
        self._measure_func: Optional[Callable[[str], float]] = None

    # ── 公开接口 ───────────────────────────────────────────────

    def set_render_area(self, rect: QRect) -> None:
        """设置渲染区域。

        通常在窗口创建或显示器变化时调用。

        Args:
            rect: 渲染区域矩形（通常等于窗口 client rect）。
        """
        self._render_area = QRect(rect)
        self._max_tracks = self._calc_max_tracks()

    def start(self) -> None:
        """启动帧渲染循环。

        启动 QTimer，开始周期性调用 _on_frame()。
        调用前应确保已通过 set_render_area() 设置渲染区域。
        """
        self._last_frame_time = time.monotonic()
        self._running = True
        self._timer.start(self.FRAME_INTERVAL)

    def stop(self) -> None:
        """停止帧渲染循环。

        停止 QTimer，保留当前活跃弹幕状态。
        再次调用 start() 可恢复渲染。
        """
        self._running = False
        self._timer.stop()

    def enqueue(self, items: List[DanmakuItem]) -> None:
        """接收新弹幕并加入活跃列表。

        从 danmaku_queue.tick() 获取应发射的弹幕，过滤 mode 后
        创建 ActiveDanmaku 并分配到对应轨道。

        v0.2 仅处理 mode=1 (滚动弹幕)。mode=4/5 的数据保留在
        DanmakuItem 中但不渲染。

        不做内容级去重 — 相同文本不同 danmaku_id 的弹幕全部保留。

        Args:
            items: 本帧新发射的弹幕列表。
        """
        for item in items:
            if item.mode == 1:
                self._add_scrolling(item)
            # mode=4/5: v0.2 不渲染，静默跳过
            # v0.3+ 将处理顶部/底部弹幕

    def clear(self) -> None:
        """清空所有活跃弹幕和轨道状态。

        适用于视频切换/连接断开等需要重置渲染状态的场景。
        """
        self._active.clear()
        self._tracks.clear()

    def render(self, painter: QPainter, rect: QRect) -> None:
        """绘制所有活跃弹幕。

        在 paintEvent 或渲染回调中调用。绘制顺序为入队顺序，
        先入队的弹幕先绘制（在底层）。

        Args:
            painter: QPainter 实例（已 begin，由调用方管理 end）。
            rect: 渲染区域（保留参数，v0.3+ 可能用于裁剪优化）。
        """
        if not self._active:
            return

        painter.save()

        # 字体
        painter.setFont(self._font)

        for dm in self._active:
            self._draw_danmaku(painter, dm)

        painter.restore()

    # ── 属性 ───────────────────────────────────────────────────

    @property
    def active_count(self) -> int:
        """当前活跃弹幕数量。"""
        return len(self._active)

    @property
    def track_count(self) -> int:
        """当前已分配的轨道数量。"""
        return len(self._tracks)

    @property
    def is_running(self) -> bool:
        """帧渲染是否正在运行。"""
        return self._running

    # ── 帧驱动 ─────────────────────────────────────────────────

    def _on_frame(self) -> None:
        """帧更新回调（QTimer 触发）。

        1. 计算帧间时差
        2. 更新所有活跃弹幕位置
        3. 移除越界弹幕
        4. 发射 frame_rendered 信号
        """
        now = time.monotonic()
        delta = now - self._last_frame_time
        self._last_frame_time = now

        # 防止异常大的 delta（如系统休眠后恢复）
        if delta > 1.0:
            delta = self.FRAME_INTERVAL / 1000.0

        self._update_positions(delta)
        self._remove_out_of_bounds()

        self.frame_rendered.emit()

    # ── 弹幕生命周期 ───────────────────────────────────────────

    def _add_scrolling(self, item: DanmakuItem) -> None:
        """创建滚动弹幕并分配轨道。

        Args:
            item: 待渲染的弹幕数据。
        """
        text_width = self._measure_text_width(item.content)

        # 分配轨道
        track = self._find_track(text_width)
        if track < 0:
            # 无可用轨道，丢弃此弹幕（v0.2 行为）
            # v0.3+ 可能实现: 延迟到下一帧重试
            return

        # 初始 x: 窗口右边缘
        start_x = float(self._render_area.width())

        # y: 轨道顶部 + baseline 偏移
        baseline_y = float(
            track * self.track_height_px + self._font_metrics_or_default().ascent()
        )

        dm = ActiveDanmaku(
            item=item,
            x=start_x,
            y=baseline_y,
            width=text_width,
            track=track,
            speed=self.SCROLL_SPEED,
        )

        self._active.append(dm)
        self._tracks[track].append(dm)

    def _find_track(self, text_width: float) -> int:
        """为一条新弹幕分配轨道 (first-fit 算法)。

        遍历现有轨道，返回第一个满足条件的轨道编号:
            - 轨道为空，或
            - 轨道上最后一条弹幕已移过足够距离，不会与新弹幕重叠
              (last.x + last.width < render_area.width() - text_width - TRACK_GAP)

        若现有轨道均不满足，且未达最大轨道数，则创建新轨道。

        Args:
            text_width: 新弹幕的像素宽度。

        Returns:
            分配的轨道编号，-1 表示无可用轨道。
        """
        threshold = self._render_area.width() - text_width - self.TRACK_GAP

        for i, track in enumerate(self._tracks):
            if not track:
                # 空轨道 — 直接使用
                return i
            # 检查轨道上最后一条弹幕是否已移过阈值
            last = track[-1]
            if last.x + last.width < threshold:
                return i

        # 无空闲轨道 — 尝试创建新轨道
        if len(self._tracks) < self._max_tracks:
            new_idx = len(self._tracks)
            self._tracks.append([])
            return new_idx

        return -1

    def _update_positions(self, delta: float) -> None:
        """更新所有活跃弹幕的 x 坐标。

        x -= speed * delta，向左移动。

        Args:
            delta: 自上一帧以来的时间间隔（秒）。
        """
        if not delta:
            return
        for dm in self._active:
            dm.x -= dm.speed * delta

    def _remove_out_of_bounds(self) -> None:
        """移除已完全移出左边界外的弹幕。

        判定条件: x + width <= 0（弹幕右边缘已移出窗口左边界）。
        同时清理轨道列表中的对应引用。
        """
        before = len(self._active)
        self._active = [dm for dm in self._active if dm.x + dm.width > 0]

        # 清理各轨道的过期引用
        for track in self._tracks:
            track[:] = [dm for dm in track if dm.x + dm.width > 0]

    # ── 绘制 ───────────────────────────────────────────────────

    def _draw_danmaku(self, painter: QPainter, dm: ActiveDanmaku) -> None:
        """绘制单条弹幕（白色文字 + 黑色描边）。

        描边实现: 在文字周围 4 个方向偏移 1px 绘制黑色文字，
        再在中心绘制白色文字。简单但有效的伪描边效果。

        Args:
            painter: QPainter 实例。
            dm: 待绘制的活跃弹幕。
        """
        x = dm.x
        y = dm.y
        text = dm.item.content

        # 黑色描边（四向阴影）
        painter.setPen(self.OUTLINE_COLOR)
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            painter.drawText(QPointF(x + dx, y + dy), text)

        # 白色主体
        painter.setPen(self.TEXT_COLOR)
        painter.drawText(QPointF(x, y), text)

    # ── 辅助方法 ───────────────────────────────────────────────

    def _measure_text_width(self, text: str) -> float:
        """测量文字像素宽度。

        优先使用注入的测量函数（便于测试），否则使用 QFontMetrics。

        Args:
            text: 待测量文字。

        Returns:
            文字像素宽度。
        """
        if self._measure_func is not None:
            return self._measure_func(text)
        return self._font_metrics_or_default().horizontalAdvance(text)

    def _font_metrics_or_default(self) -> QFontMetrics:
        """获取 QFontMetrics 实例（延迟创建）。

        QFontMetrics 需要 QApplication 已创建，因此延迟到首次使用时初始化。
        """
        if self._font_metrics is None:
            self._font_metrics = QFontMetrics(self._font)
        return self._font_metrics

    @property
    def track_height_px(self) -> int:
        """单条轨道高度 (px)。"""
        return self.DEFAULT_FONT_SIZE + self.TRACK_PADDING

    def _calc_max_tracks(self) -> int:
        """根据当前渲染区域高度计算最大轨道数。"""
        return max(1, self._render_area.height() // self.track_height_px)
