# main_window.py — BiliDanmaku 透明覆盖窗口
# 提供全屏透明无边框置顶窗口，作为弹幕渲染的画布层。
#
# 设计原则:
#   - 纯窗口管理: 只管窗口属性（透明/置顶/鼠标穿透/全屏），不处理弹幕渲染。
#     弹幕绘制由 danmaku_renderer (v0.2.2+) 通过 paint 回调或子 widget 接入。
#   - 平台适配: Windows 使用 Win32 API 实现鼠标穿透，非 Windows 平台降级为
#     Qt.WindowType.SubWindow（无法穿透但窗口仍可用）。
#   - 延迟初始化: winId() 在 show() 后才能获取有效的 HWND，因此鼠标穿透
#     在 showEvent 中设置，避免构造时调用 winId() 导致创建原生窗口。
#   - 零业务依赖: 不依赖 events / data_dispatcher / danmaku 模块。
#
# 用法:
#   app = QApplication(sys.argv)
#   window = TransparentOverlay()
#   window.show()
#   # 后续版本:
#   #   renderer = DanmakuRenderer(window)
#   #   window.set_renderer(renderer)
#   app.exec()
#
# 依赖: PyQt6, ctypes (Windows only)

from __future__ import annotations

import ctypes
import sys
from typing import Optional

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QFont, QScreen
from PyQt6.QtWidgets import QWidget, QApplication

# ── Win32 常量 (仅 Windows 使用) ───────────────────────────────────

# GetWindowLongW / SetWindowLongW 索引
GWL_EXSTYLE = -20

# 扩展窗口样式
WS_EX_LAYERED = 0x00080000    # 分层窗口 (需配合 SetLayeredWindowAttributes 或 UpdateLayeredWindow)
WS_EX_TRANSPARENT = 0x00000020  # 鼠标穿透: 鼠标事件透传到下层窗口
WS_EX_TOOLWINDOW = 0x00000080   # 工具窗口: 不显示在任务栏和 Alt+Tab 列表


class TransparentOverlay(QWidget):
    """全屏透明无边框置顶窗口。

    作为弹幕渲染的画布。窗口本身不绘制任何内容 — 像素由后续版本
    的 DanmakuRenderer 通过 QPainter 绘制（通过 paintEvent 回调或
    定时器驱动的 repaint 机制）。

    窗口属性:
        - FramelessWindowHint: 无标题栏和边框
        - WindowStaysOnTopHint: 始终在常规窗口之上
        - Tool: 不在任务栏显示独立条目
        - WA_TranslucentBackground: 透明背景
        - 全屏覆盖 (primaryScreen geometry)

    v0.2.2+ 渲染接入预留接口:
        - paintEvent() — 可被 override 或设置回调
        - render_callback — 可选的外部绘制函数
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化透明覆盖窗口。

        Args:
            parent: 父 widget。通常为 None（独立顶层窗口）。
        """
        super().__init__(parent)

        # ── 窗口标志 ──────────────────────────────────────────
        # Tool 属性: 在 Windows 上不显示任务栏按钮，行为类似工具窗口
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint      # 无边框
            | Qt.WindowType.WindowStaysOnTopHint   # 始终置顶
            | Qt.WindowType.Tool                    # 工具窗口
            | Qt.WindowType.SubWindow               # 子窗口级别
        )

        # ── 透明背景 ──────────────────────────────────────────
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # 确保窗口本身不绘制不透明背景
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        # ── 全屏尺寸 ──────────────────────────────────────────
        # 覆盖主显示器全部区域
        app = QApplication.instance()
        if app:
            screen: QScreen = app.primaryScreen() or app.screens()[0]
            self.setGeometry(screen.geometry())
        else:
            # 回退: 1920x1080 (无 QApplication 实例时，仅测试场景)
            self.setGeometry(0, 0, 1920, 1080)

        # ── 渲染接入预留 ──────────────────────────────────────
        # v0.2.2+: 外部渲染回调 (callable 或 DanmakuRenderer)
        # 签名: callable(QPainter, QRect) -> None
        self._render_callback: Optional[callable] = None

        # ── 鼠标穿透状态 ──────────────────────────────────────
        self._mouse_passthrough_enabled = False

    # ── Qt 事件 ─────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        """窗口显示事件 — 在此获取有效的原生窗口句柄并设置鼠标穿透。

        winId() 必须在 show() 后调用才能返回有效的 HWND。
        """
        super().showEvent(event)
        if sys.platform == 'win32' and not self._mouse_passthrough_enabled:
            self._enable_mouse_passthrough()

    # ── 公开接口 ───────────────────────────────────────────────

    def refresh_geometry(self) -> None:
        """刷新窗口几何为当前主显示器尺寸。

        当显示器分辨率变化或窗口从其他显示器切换时调用。
        """
        app = QApplication.instance()
        if app:
            screen: QScreen = app.primaryScreen() or app.screens()[0]
            self.setGeometry(screen.geometry())

    def render_area(self) -> QRect:
        """返回可渲染区域矩形。

        Returns:
            QRect: 窗口的客户区矩形 (通常等于屏幕尺寸)。
        """
        return self.rect()

    def set_renderer(self, callback: callable) -> None:
        """设置外部渲染回调 (v0.2.2+ 占位)。

        Args:
            callback: 签名为 callback(painter: QPainter, rect: QRect) -> None 的可调用对象。
        """
        self._render_callback = callback

    def is_mouse_passthrough(self) -> bool:
        """返回鼠标穿透是否已启用。

        Returns:
            bool: 鼠标穿透状态。
        """
        return self._mouse_passthrough_enabled

    # ── 内部实现 ───────────────────────────────────────────────

    def _enable_mouse_passthrough(self) -> None:
        """启用 Windows 鼠标穿透。

        设置 WS_EX_TRANSPARENT 扩展样式，使所有鼠标事件透传到
        窗口下方的其他应用程序。

        仅在 Windows 平台有效。Unix/macOS 上此方法为 no-op。
        """
        if sys.platform != 'win32':
            return

        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32

            # 获取当前扩展样式
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

            # 添加三层标志
            new_style = (
                ex_style
                | WS_EX_LAYERED       # 分层窗口
                | WS_EX_TRANSPARENT   # 鼠标穿透
                | WS_EX_TOOLWINDOW    # 工具窗口
            )

            result = user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            if result == 0:
                # GetLastError 可能有助于诊断
                error = ctypes.get_last_error()
                if error != 0:
                    import sys as _sys
                    print(
                        f'[BiliDanmaku] main_window: SetWindowLongW 返回 0, '
                        f'GetLastError={error}',
                        file=_sys.stderr,
                    )
            else:
                self._mouse_passthrough_enabled = True

        except Exception:
            # 鼠标穿透是便利功能，不应导致程序崩溃
            import sys as _sys
            print(
                '[BiliDanmaku] main_window: 无法设置鼠标穿透',
                file=_sys.stderr,
            )
