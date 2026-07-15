# overlay/__init__.py — BiliDanmaku PyQt Overlay 层
# 桌面透明弹幕显示子系统。
#
# v0.2.x 当前模块:
#   - main_window:      透明无边框置顶窗口 + 鼠标穿透 + paintEvent 渲染回调
#   - tray_icon:        系统托盘图标 + 基础菜单 (退出)
#   - danmaku_renderer: QPainter 弹幕渲染引擎 + first-fit 多轨道 + QTimer 帧驱动
#   - danmaku_queue:    弹幕缓冲队列 + 墙上时钟发射 + 线程安全
#
# 依赖: PyQt6 (QtWidgets, QtGui, QtCore)
