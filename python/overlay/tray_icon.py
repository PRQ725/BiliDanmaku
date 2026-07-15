# tray_icon.py — BiliDanmaku 系统托盘图标
# 提供系统托盘入口，展示基础右键菜单（退出程序）。
#
# 设计原则:
#   - 托盘是程序的主要用户交互入口（v0.2 阶段仅提供退出功能）。
#   - 图标通过 QPainter 程序化生成（v0.2 无外部图标资源，v0.3+ 替换为资源文件）。
#   - 零业务依赖: 不依赖 events / data_dispatcher / danmaku 模块。
#   - 生命周期跟随 QApplication，不需要手动管理。
#
# v0.3+ 将扩展:
#   - 弹幕开关
#   - 样式配置
#   - 透明度调节
#
# 用法:
#   app = QApplication(sys.argv)
#   tray = TrayIcon()
#   tray.show()
#   app.exec()  # 托盘退出时调用 QApplication.quit()
#
# 依赖: PyQt6

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QAction
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication


def _create_programmatic_icon(size: int = 32) -> QIcon:
    """创建程序化图标（圆形 + "弹"字）。

    在 v0.3+ 引入外部图标资源前，使用 QPainter 绘制一个简单的
    识别图标，避免依赖缺失的 .png 文件。

    Args:
        size: 图标尺寸 (像素)，默认 32x32。

    Returns:
        QIcon: 绘制完成的图标。
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # 背景圆: B站粉色
    margin = 2
    painter.setBrush(QColor('#FB7299'))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)

    # 前景文字: "弹" (白色)
    painter.setPen(QColor(255, 255, 255))
    font = QFont('Microsoft YaHei', size // 2)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, '弹')

    painter.end()
    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    """BiliDanmaku 系统托盘图标。

    提供托盘图标显示和右键上下文菜单。当前菜单仅包含「退出」操作。

    属性:
        icon (QIcon): 托盘图标。
        menu (QMenu): 右键上下文菜单。
    """

    def __init__(self, parent: QApplication | None = None) -> None:
        """初始化托盘图标。

        Args:
            parent: 父对象。传入 QApplication 实例可确保托盘跟随应用生命期。
        """
        # ── 图标 ──────────────────────────────────────────────
        icon = _create_programmatic_icon()
        super().__init__(icon, parent)

        # ── 提示文字 ──────────────────────────────────────────
        self.setToolTip('BiliDanmaku — B站弹幕助手')

        # ── 右键菜单 ──────────────────────────────────────────
        self._menu = QMenu()
        self._build_menu()
        self.setContextMenu(self._menu)

    # ── 公开接口 ───────────────────────────────────────────────

    def menu(self) -> QMenu:
        """返回右键上下文菜单。

        Returns:
            QMenu: 当前上下文菜单实例。
        """
        return self._menu

    # ── 内部实现 ───────────────────────────────────────────────

    def _build_menu(self) -> None:
        """构建右键菜单内容。

        当前菜单项:
            - 退出 (QApplication.quit)
        v0.3+ 将新增: 弹幕开关、样式设置、透明度滑块。
        """
        quit_action = QAction('退出', self._menu)
        quit_action.triggered.connect(self._on_quit)
        self._menu.addAction(quit_action)

    def _on_quit(self) -> None:
        """退出程序。

        调用 QApplication.quit() 发送退出信号。
        这会触发:
            - 所有顶层窗口关闭
            - QApplication.exec() 返回
            - 进程正常退出
        """
        QApplication.quit()
