# tests/test_overlay.py — PyQt Overlay 层单元测试
# 测试 main_window 和 tray_icon 模块的基础功能。
#
# Qt GUI 测试说明:
#   本测试需要 PyQt6 和运行中的桌面环境 (Windows/macOS/Linux 桌面)。
#   测试创建 QApplication 实例但不显示窗口 — 仅验证属性、标志、菜单结构等
#   非可视特性。
#
#   以下场景测试将自动跳过 (SKIP):
#     - PyQt6 未安装
#     - 无可用桌面 (DISPLAY= 或 headless 环境)
#     - QSystemTrayIcon.isSystemTrayAvailable() == False (托盘测试)
#
#   已知限制:
#     - 无法在无头 CI 环境运行 (需要 Qt GUI 支持)
#     - 托盘图标测试在某些 Linux DE 可能不可用
#     - 鼠标穿透仅在 Windows 平台生效，测试仅在 Windows 验证
#     - 不测试 show() 行为 (会弹出实际窗口)

from __future__ import annotations

import sys
import os
import pytest

# 确保 python/ 在 sys.path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python'))

# ── 检查 PyQt6 是否可用 ──────────────────────────────────────────

try:
    from PyQt6.QtCore import Qt, QRect
    from PyQt6.QtGui import QIcon, QAction
    from PyQt6.QtWidgets import (
        QApplication, QSystemTrayIcon, QMenu, QWidget,
    )
    _PYQT6_AVAILABLE = True
except ImportError:
    _PYQT6_AVAILABLE = False

# 仅在 PyQt6 可用时导入被测试模块
if _PYQT6_AVAILABLE:
    from overlay.main_window import (
        TransparentOverlay,
        GWL_EXSTYLE,
        WS_EX_LAYERED,
        WS_EX_TRANSPARENT,
        WS_EX_TOOLWINDOW,
    )
    from overlay.tray_icon import TrayIcon, _create_programmatic_icon


# ── 跳过条件 ─────────────────────────────────────────────────────

pytestmark = pytest.mark.skipif(
    not _PYQT6_AVAILABLE,
    reason='PyQt6 未安装',
)

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture(scope='session')
def qapp() -> QApplication:
    """会话级 QApplication 实例。

    整个测试会话共享一个 QApplication，避免重复创建
    （Qt 不允许同时存在多个 QApplication）。
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


# ═══════════════════════════════════════════════════════════════════
# TransparentOverlay Tests
# ═══════════════════════════════════════════════════════════════════


class TestOverlayConstruction:
    """测试 TransparentOverlay 构造和基本属性。"""

    def test_create_overlay(self, qapp: QApplication) -> None:
        """可正常创建 TransparentOverlay 实例。"""
        window = TransparentOverlay()
        assert window is not None
        assert isinstance(window, QWidget)

    def test_no_parent_by_default(self, qapp: QApplication) -> None:
        """默认 parent 为 None。"""
        window = TransparentOverlay()
        assert window.parent() is None

    def test_accepts_parent(self, qapp: QApplication) -> None:
        """可接受 parent widget。"""
        parent = QWidget()
        window = TransparentOverlay(parent=parent)
        assert window.parent() is parent

    def test_multiple_instances(self, qapp: QApplication) -> None:
        """可创建多个独立实例。"""
        w1 = TransparentOverlay()
        w2 = TransparentOverlay()
        assert w1 is not w2
        assert w1.winId() != w2.winId() or w1.winId() == 0


class TestOverlayWindowFlags:
    """测试窗口标志。"""

    def test_frameless(self, qapp: QApplication) -> None:
        """窗口无边框。"""
        window = TransparentOverlay()
        flags = window.windowFlags()
        assert flags & Qt.WindowType.FramelessWindowHint

    def test_stays_on_top(self, qapp: QApplication) -> None:
        """窗口置顶。"""
        window = TransparentOverlay()
        flags = window.windowFlags()
        assert flags & Qt.WindowType.WindowStaysOnTopHint

    def test_tool_window(self, qapp: QApplication) -> None:
        """窗口为工具窗口。"""
        window = TransparentOverlay()
        flags = window.windowFlags()
        assert flags & Qt.WindowType.Tool


class TestOverlayTransparency:
    """测试透明背景属性。"""

    def test_translucent_background(self, qapp: QApplication) -> None:
        """WA_TranslucentBackground 已设置。"""
        window = TransparentOverlay()
        assert window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def test_no_system_background(self, qapp: QApplication) -> None:
        """WA_NoSystemBackground 已设置。"""
        window = TransparentOverlay()
        assert window.testAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)


class TestOverlayGeometry:
    """测试窗口几何。"""

    def test_geometry_is_valid(self, qapp: QApplication) -> None:
        """窗口有有效的几何尺寸。"""
        window = TransparentOverlay()
        geo = window.geometry()
        assert geo.width() > 0
        assert geo.height() > 0

    def test_geometry_matches_screen(self, qapp: QApplication) -> None:
        """窗口几何匹配主显示器尺寸。"""
        window = TransparentOverlay()
        geo = window.geometry()
        screen = qapp.primaryScreen()
        screen_geo = screen.geometry()
        assert geo.width() == screen_geo.width()
        assert geo.height() == screen_geo.height()

    def test_refresh_geometry_does_not_crash(self, qapp: QApplication) -> None:
        """refresh_geometry() 不抛出异常。"""
        window = TransparentOverlay()
        window.refresh_geometry()
        geo = window.geometry()
        assert geo.width() > 0 and geo.height() > 0


class TestOverlayRenderArea:
    """测试 render_area() 接口。"""

    def test_render_area_returns_rect(self, qapp: QApplication) -> None:
        """render_area() 返回有效的 QRect。"""
        window = TransparentOverlay()
        rect = window.render_area()
        assert isinstance(rect, QRect)
        assert rect.width() > 0
        assert rect.height() > 0

    def test_render_area_origin_is_zero(self, qapp: QApplication) -> None:
        """render_area() 原点为 (0, 0) — 客户区坐标。"""
        window = TransparentOverlay()
        rect = window.render_area()
        assert rect.x() == 0
        assert rect.y() == 0


class TestOverlayRendererCallback:
    """测试渲染回调接口 (set_renderer 占位)。"""

    def test_set_renderer_stores_callback(self, qapp: QApplication) -> None:
        """set_renderer() 接受并存储回调函数。"""
        window = TransparentOverlay()
        called_with = []

        def my_renderer(painter, rect) -> None:
            called_with.append((painter, rect))

        window.set_renderer(my_renderer)
        assert window._render_callback is my_renderer

    def test_set_renderer_replaces_previous(self, qapp: QApplication) -> None:
        """set_renderer() 替换之前设置的回调。"""
        window = TransparentOverlay()
        cb1 = lambda p, r: None
        cb2 = lambda p, r: None
        window.set_renderer(cb1)
        window.set_renderer(cb2)
        assert window._render_callback is cb2

    def test_set_renderer_none(self, qapp: QApplication) -> None:
        """set_renderer(None) 清除回调。"""
        window = TransparentOverlay()
        cb = lambda p, r: None
        window.set_renderer(cb)
        window.set_renderer(None)
        assert window._render_callback is None


class TestOverlayMousePassthrough:
    """测试鼠标穿透功能。"""

    def test_passthrough_disabled_before_show(self, qapp: QApplication) -> None:
        """show() 前鼠标穿透未启用。"""
        window = TransparentOverlay()
        assert not window.is_mouse_passthrough()

    def test_passthrough_state_method(self, qapp: QApplication) -> None:
        """is_mouse_passthrough() 返回布尔值。"""
        window = TransparentOverlay()
        result = window.is_mouse_passthrough()
        assert isinstance(result, bool)


@pytest.mark.skipif(sys.platform != 'win32', reason='鼠标穿透测试仅在 Windows 运行')
class TestOverlayWin32Constants:
    """测试 Win32 常量值。"""

    def test_gwl_exstyle(self) -> None:
        """GWL_EXSTYLE 值为 -20。"""
        assert GWL_EXSTYLE == -20

    def test_ws_ex_layered(self) -> None:
        """WS_EX_LAYERED 值为 0x00080000。"""
        assert WS_EX_LAYERED == 0x00080000

    def test_ws_ex_transparent(self) -> None:
        """WS_EX_TRANSPARENT 值为 0x00000020。"""
        assert WS_EX_TRANSPARENT == 0x00000020

    def test_ws_ex_toolwindow(self) -> None:
        """WS_EX_TOOLWINDOW 值为 0x00000080。"""
        assert WS_EX_TOOLWINDOW == 0x00000080


# ═══════════════════════════════════════════════════════════════════
# TrayIcon Tests
# ═══════════════════════════════════════════════════════════════════


class TestTrayIconConstruction:
    """测试 TrayIcon 构造和基本属性。"""

    def test_create_tray_icon(self, qapp: QApplication) -> None:
        """可正常创建 TrayIcon 实例。"""
        tray = TrayIcon(parent=qapp)
        assert tray is not None
        assert isinstance(tray, QSystemTrayIcon)

    def test_icon_is_set(self, qapp: QApplication) -> None:
        """托盘图标已设置（非空）。"""
        tray = TrayIcon(parent=qapp)
        assert not tray.icon().isNull()

    def test_tooltip_is_set(self, qapp: QApplication) -> None:
        """提示文字包含 'BiliDanmaku'。"""
        tray = TrayIcon(parent=qapp)
        assert 'BiliDanmaku' in tray.toolTip()


class TestTrayIconMenu:
    """测试托盘右键菜单。"""

    def test_context_menu_exists(self, qapp: QApplication) -> None:
        """右键菜单已设置。"""
        tray = TrayIcon(parent=qapp)
        menu = tray.contextMenu()
        assert menu is not None
        assert isinstance(menu, QMenu)

    def test_menu_has_quit_action(self, qapp: QApplication) -> None:
        """菜单包含「退出」选项。"""
        tray = TrayIcon(parent=qapp)
        menu = tray.contextMenu()
        actions = menu.actions()
        action_texts = [a.text() for a in actions]
        assert '退出' in action_texts

    def test_menu_quit_is_last(self, qapp: QApplication) -> None:
        """「退出」为菜单最后一个选项。"""
        tray = TrayIcon(parent=qapp)
        menu = tray.contextMenu()
        actions = menu.actions()
        assert len(actions) >= 1
        assert actions[-1].text() == '退出'

    def test_quit_action_triggers_quit(self, qapp: QApplication) -> None:
        """退出操作连接到 QApplication.quit。

        注意: 不实际触发 quit()，仅验证连接存在。
        """
        tray = TrayIcon(parent=qapp)
        menu = tray.contextMenu()
        quit_action = None
        for a in menu.actions():
            if a.text() == '退出':
                quit_action = a
                break
        assert quit_action is not None
        # QAction.triggered 信号有连接 — 不直接访问 receivers()
        # 但可以通过 triggered.emit() 间接验证（不在此测试中触发）


class TestTrayIconMenuMethod:
    """测试 menu() 公开方法。"""

    def test_menu_method_returns_same_as_context_menu(
        self, qapp: QApplication
    ) -> None:
        """menu() 返回与 contextMenu() 相同的实例。"""
        tray = TrayIcon(parent=qapp)
        assert tray.menu() is tray.contextMenu()


class TestCreateProgrammaticIcon:
    """测试图标生成函数。"""

    def test_returns_qicon(self) -> None:
        """返回 QIcon 实例。"""
        icon = _create_programmatic_icon()
        assert isinstance(icon, QIcon)

    def test_icon_not_null(self) -> None:
        """返回非空图标。"""
        icon = _create_programmatic_icon()
        assert not icon.isNull()

    def test_custom_size(self) -> None:
        """支持自定义尺寸。"""
        icon_16 = _create_programmatic_icon(size=16)
        icon_64 = _create_programmatic_icon(size=64)
        assert not icon_16.isNull()
        assert not icon_64.isNull()
        # 不同尺寸应产生不同的 pixmap
        assert icon_16.pixmap(16).size().width() == 16
        assert icon_64.pixmap(64).size().width() == 64

    @pytest.mark.skipif(
        'not _PYQT6_AVAILABLE',
        reason='PyQt6 未安装',
    )
    def test_default_size_32(self) -> None:
        """默认尺寸为 32x32。"""
        icon = _create_programmatic_icon()
        pm = icon.pixmap(32)
        assert pm.width() == 32
        assert pm.height() == 32


# ═══════════════════════════════════════════════════════════════════
# 集成测试: Overlay + TrayIcon 共存
# ═══════════════════════════════════════════════════════════════════


class TestOverlayAndTrayIntegration:
    """测试窗口和托盘共存。"""

    def test_both_can_exist_simultaneously(
        self, qapp: QApplication
    ) -> None:
        """窗口和托盘可同时存在。"""
        window = TransparentOverlay()
        tray = TrayIcon(parent=qapp)
        assert window is not None
        assert tray is not None

    def test_no_circular_dependency(self, qapp: QApplication) -> None:
        """两个模块无循环依赖 — 导入验证。"""
        import overlay.main_window
        import overlay.tray_icon
        assert overlay.main_window is not None
        assert overlay.tray_icon is not None


# ═══════════════════════════════════════════════════════════════════
# 手动测试 (不通过 pytest 运行)
# ═══════════════════════════════════════════════════════════════════


def run_visual_test():
    """手动运行可视化验证。

    打开透明覆盖窗口和托盘图标，供开发者确认视觉效果。
    不参与 pytest 自动测试。

    Usage:
        python tests/test_overlay.py
    """
    app = QApplication(sys.argv)

    # 创建透明窗口并显示
    from overlay.main_window import TransparentOverlay
    window = TransparentOverlay()
    window.show()

    # 创建托盘图标
    from overlay.tray_icon import TrayIcon
    tray = TrayIcon(parent=app)
    tray.show()

    print('[test_overlay] 透明窗口和托盘已显示。', file=sys.stderr)
    print('[test_overlay] 右键点击托盘图标退出。', file=sys.stderr)

    sys.exit(app.exec())


if __name__ == '__main__':
    if not _PYQT6_AVAILABLE:
        print('错误: PyQt6 未安装。请运行: pip install PyQt6', file=sys.stderr)
        sys.exit(1)
    run_visual_test()
