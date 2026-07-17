# BiliDanmaku

## 项目目标

开发一个桌面 B站弹幕助手。

用户通过 Chrome/Edge 浏览器观看 B站视频，
浏览器扩展负责识别视频状态，
Python Native Host 获取弹幕，
PyQt6 Overlay 显示桌面弹幕。

---

# 架构说明

项目由三个主要部分组成：

## Extension

位置：`extension/`

| 文件 | 职责 |
|------|------|
| `manifest.json` | Manifest V3 扩展清单 |
| `content.js` | Resolver Chain 提取 BV/cid/title/duration；PlaybackMonitor 轮询播放进度；pagehide 发送 video_unload |
| `background.js` | Service Worker — 惰性连接、消息路由、状态持久化 (chrome.storage.local)、重连退避 |

职责：
- 检测 B站视频页面
- 获取 BV号、CID、播放状态
- 监听页面生命周期
- 通过 Native Messaging 发送事件

禁止：
- 处理弹幕业务逻辑
- 直接管理 Python 状态

## Python Native Host

位置：`python/`

| 文件 | 职责 |
|------|------|
| `native_host.py` | 主入口 — QApplication、stdin 协议、DanmakuIntegration 桥接、主循环 |
| `events.py` | EventType 枚举 + 4 个事件 @dataclass (纯数据，无逻辑) |
| `data_dispatcher.py` | 线程安全发布-订阅事件总线 (同步分发) |
| `danmaku_fetcher.py` | B站弹幕 API HTTP 请求 (urllib + deflate/gzip) |
| `danmaku_parser.py` | XML → List[DanmakuItem] 解析 |
| `danmaku_handler.py` | 编排: cid 确认 → 获取 → 解析 → 发布 DanmakuLoadedEvent |
| `video_info_handler.py` | BV→cid API 调用 + 内存缓存 |
| `constants.py` | API 端点、HTTP headers、超时配置 |
| `overlay/main_window.py` | PyQt6 透明置顶窗口 (Win32 鼠标穿透) |
| `overlay/danmaku_renderer.py` | QPainter 滚动弹幕渲染 (QTimer ~30fps, first-fit 轨道) |
| `overlay/danmaku_queue.py` | 线程安全弹幕缓冲队列 (墙上时钟驱动, 索引指针发射) |
| `overlay/tray_icon.py` | 系统托盘图标 + 退出菜单 |

职责：
- 接收 Extension 消息
- 获取 B站弹幕
- 管理事件分发
- 管理渲染生命周期

禁止：
- 依赖浏览器 DOM

## Renderer

位置：`python/overlay/`

职责：
- PyQt6 透明窗口
- 弹幕动画
- 渲染状态管理

禁止：
- 处理网络请求
- 处理浏览器事件

---

# 关键架构约束

## 线程模型

项目使用 **双线程** 架构：

```
Background Thread (daemon):        GUI Thread (Qt main):
  stdin read loop                    QApplication
  → handle_message()                 → overlay 模块 (Window, Renderer)
  → danmaku_handler (HTTP)           → DanmakuIntegration (QObject)
  → dispatcher.publish(event)        → _on_frame() 每帧回调
```

**Dispatcher 回调在发布者线程执行。** 即 `DanmakuIntegration` 的 `_on_danmaku_loaded()` 和 `_on_video_unload()` 在**后台线程**运行。

**跨线程桥接模式：**

| 机制 | 方向 | 用途 |
|------|------|------|
| `_pending_clear` flag | 后台线程 set → GUI 线程 check+consume | 安全地在 GUI 线程调用 `renderer.clear()` |
| `quit_requested` pyqtSignal | 后台线程 emit → GUI 线程 | stdin 断开时安全退出 QApplication |
| `renderer.frame_rendered` pyqtSignal | GUI 线程 emit → GUI 线程 | 每帧驱动 `_on_frame()` |

**线程安全规则：**
- `window.hide()` / `window.show()` / `renderer.clear()` / `renderer.enqueue()` 仅从 GUI 线程调用
- `queue.load()` / `queue.clear()` / `queue.tick()` 自身有 Lock，任意线程安全
- `dispatcher.publish()` 自身有 Lock，任意线程安全
- **不要**在后台线程直接操作 Qt 对象

## 事件系统

`DataDispatcher` (module-level singleton `dispatcher`) — 同步分发，订阅者在发布者线程执行。

`EventType` 枚举与 `@dataclass` 事件一一对应，通过命名约定自动推断：

| 事件类 | EventType | 触发场景 |
|--------|-----------|----------|
| `VideoSwitchedEvent` | `VIDEO_SWITCHED` | 浏览器检测到新视频 |
| `DanmakuLoadedEvent` | `DANMAKU_LOADED` | 弹幕获取+解析完成 |
| `ProgressUpdatedEvent` | `PROGRESS_UPDATED` | 浏览器进度更新 (v0.2 预留) |
| `VideoUnloadEvent` | `VIDEO_UNLOAD` | 页面关闭/导航离开 (pagehide) |

事件类为纯数据 @dataclass，不包含任何业务逻辑，不依赖 PyQt。

## 渲染管线

```
QTimer (~30fps) → renderer._on_frame()
  → frame_rendered.emit()
    → DanmakuIntegration._on_frame()     ← GUI 线程
      1. check _pending_clear → renderer.clear()
      2. check _wall_clock_start → window.hide()/show()
      3. queue.tick(elapsed) → 新弹幕
      4. renderer.enqueue(new_items)
      5. window.update() → QPainter 绘制
```

**Renderer 关键参数：**
- 帧间隔: 33ms (~30fps)
- 轨道间隔: 80px (TRACK_GAP)
- 最大轨道数: 屏幕高度 / (字号 + 间距)
- v0.2 仅渲染 mode=1 (滚动弹幕)，mode=4/5 静默跳过
- 帧内 try/except 保护 — 单帧异常不停止 QTimer
- 30s 心跳诊断: `[renderer heartbeat] frame=#N active=N running=True/False`

**DanmakuQueue 关键行为：**
- 按 `time` 升序排列，索引指针 `_next_index` 单调递增
- `tick(elapsed)` 返回 `time <= elapsed` 且尚未发射的弹幕
- 每条弹幕仅发射一次，索引不回溯
- `load()` 隐含 `clear()` — 替换全部数据并重置指针
- 容量上限 2000 条 (按最早弹幕截断)

## Extension 边界

**惰性连接：** `connectNative()` 仅在收到 B站视频消息时才调用。平时不浏览 B站 = Python 进程不启动。

**消息路由：** BV 变化时发送 `video_switch`，同 BV 同 session 发送 `progress_update` (限流 1次/s)。

**状态持久化：** `chrome.storage.local` 存储 `{lastBv, timestamp}`，30 分钟过期 (`SESSION_EXPIRY_MS`)。SW 冷启动时恢复，防止虚假 video_switch。

**重连机制：** 断开后指数退避重连 (1s→2s→4s→8s→16s, cap 30s)，最多 5 次。超出后等待新的用户动作触发惰性连接。

---

# 生命周期设计原则

修改生命周期相关代码时，必须先分析：

1. 谁创建对象
2. 谁持有对象
3. 谁负责销毁
4. 是否存在残留状态

## 核心状态变量

| 变量 | 位置 | 含义 | 驱动行为 |
|------|------|------|----------|
| `_wall_clock_start` | DanmakuIntegration | `None` = 无活跃视频；`float` = 视频加载时刻 | 窗口可见性 + 帧处理 |
| `_pending_clear` | DanmakuIntegration | 后台线程请求清理渲染器 | 下一帧 `renderer.clear()` |
| `lastBv` | background.js | 上一次触发 video_switch 的 BV | 判断是否需要 re-seed |
| `_next_index` | DanmakuQueue | 下一条待发射弹幕的索引 | 单调递增，不回溯 |

## 关键生命周期路径

**启动:**
```
Chrome 打开 B站视频 → content.js Resolver Chain 成功
  → background.js 惰性 connectNative() → 启动 Python
    → native_host.py main(): QApplication → overlay 模块 → DanmakuIntegration → QTimer.start()
    → background.js 发送 video_switch → Python 获取弹幕 → 渲染
```

**关闭视频 tab:**
```
content.js pagehide 事件 → background.js video_unload
  → Python dispatcher.publish(VideoUnloadEvent)
    → _on_video_unload(): _pending_clear=True, queue.clear(), _wall_clock_start=None
    → 下一帧 _on_frame(): renderer.clear(), window.hide()
```

**视频切换:**
```
content.js 检测到新 BV → background.js video_switch
  → Python dispatcher.publish(VideoSwitchedEvent)
    → 获取新弹幕 → DanmakuLoadedEvent
      → _pending_clear=True (清旧弹幕), _wall_clock_start=now, queue.load(new_items)
      → 下一帧: renderer.clear(), window.show(), 开始渲染新弹幕
```

**关闭 Chrome:**
```
Chrome 退出 → Native Messaging port 断开
  → Python stdin 读 EOF → quit_requested.emit() → app.quit()
    → cleanup: window.hide(), renderer.stop(), renderer.clear()
```

## 重点关注

- Chrome Extension Service Worker 生命周期 (闲置 ~30s 挂起)
- Native Messaging 连接生命周期 (惰性连接、重连退避)
- Qt 窗口生命周期 (透明置顶、鼠标穿透)
- Renderer QTimer 生命周期 (start/stop 配对)
- DanmakuIntegration 订阅生命周期 (subscribe 后必须在 shutdown 时 unsubscribe)

**关闭视频后必须确保：**
- 弹幕停止
- 队列清空
- 窗口隐藏
- 不产生孤儿状态

---

# Debug 流程

遇到 Bug：**不要立即修改代码。**

先输出：
1. 当前数据流
2. 生命周期路径
3. 可能断点
4. 根因假设
5. 最小修复方案

## Extension 调试入口

| 日志来源 | 查看方式 |
|----------|----------|
| content.js `console.log` | F12 → Console (B站页面标签) |
| background.js `console.log` | `chrome://extensions` → 扩展详情 → Service Worker → Inspect views |
| Native Messaging 连接错误 | 同上 Service Worker Console |
| Native Host 注册状态 | `REG QUERY "HKCU\Software\Google\Chrome\NativeMessagingHosts\com.bili.danmaku"` |

## Python 调试入口

- **stderr 日志:** 查看 `python/native_host.log` (运行时日志文件)
- **Renderer 心跳:** 每 30s 输出 `[renderer heartbeat] frame=#N active=N running=True/False` — 判断 QTimer 是否存活、弹幕是否活跃
- **协议测试:** `python test_native_host.py` — 独立于 Chrome 测试 Native Messaging 协议
- **测试模式:** 设置环境变量 `BILIDANMAKU_TEST_MODE=1` — fetcher 返回硬编码 XML，video_info_handler 抛出 ValueError

## 常见问题定位

| 现象 | 检查点 | 排查方法 |
|------|--------|----------|
| 弹幕不出现 | Resolver Chain | F12 Console 查看 `[BiliDanmaku]` 日志 |
| | background 转发 | SW Console 查看 `sendToNative` 日志 |
| | Python 接收 | `native_host.log` 查看 `收到消息 type=` |
| | 弹幕获取 | 检查 DANMAKU_LOADED 事件的 success/total |
| | 窗口状态 | 心跳日志 `active=N`，N>0 表示有弹幕入队 |
| 窗口不消失 | video_unload 链路 | SW Console 确认 `handleVideoUnload` 被调用 |
| | _wall_clock_start | 心跳日志 + 检查 `_on_frame` 中 hide 逻辑 |
| Native Host 不启动 | 惰性连接 | SW Console 确认是否收到 B站视频消息 |
| | 注册表 | 检查 Native Host 注册表路径和 JSON |
| SW 重复发 video_switch | 状态持久化 | 检查 `lastBv` + `SESSION_EXPIRY_MS` 恢复逻辑 |

---

# 测试规范

## Python 测试

**修改 Python 代码后必须运行 pytest，全部通过。**

| 测试文件 | 框架 | 依赖 | 覆盖领域 |
|----------|------|------|----------|
| `tests/test_danmaku_parser.py` | unittest | 无 | XML 解析、DanmakuItem 字段 |
| `tests/test_dispatcher.py` | unittest | 无 | 事件订阅/发布/取消、类型推断、线程安全 |
| `tests/test_danmaku_queue.py` | pytest | 无 | 排序、tick 发射、容量截断、线程安全 |
| `tests/test_overlay.py` | pytest | PyQt6 | 窗口属性、鼠标穿透、托盘图标 |
| `tests/test_danmaku_renderer.py` | pytest | PyQt6 | 轨道分配、弹幕滚动、模式过滤、帧逻辑 |
| `tests/test_integration.py` | pytest | PyQt6 | DanmakuIntegration 完整链路、video_unload、窗口显隐 |

运行方式:
```bash
# 全部测试
python -m pytest tests/ -v

# 不需要 PyQt 的测试 (CI/快速验证)
python -m pytest tests/test_danmaku_parser.py tests/test_dispatcher.py tests/test_danmaku_queue.py -v
```

## Mock/Fake 模式

| 模式 | 用途 | 示例 |
|------|------|------|
| `renderer._measure_func` 注入 | 避免 QFontMetrics 依赖 | `lambda text: len(text) * 15.0` |
| `BILIDANMAKU_TEST_MODE` 环境变量 | 绕过 HTTP 请求 | fetcher 返回硬编码 XML |
| `monkeypatch.setattr(native_host, 'dispatcher', ...)` | 隔离 dispatcher | 测试独立 DataDispatcher 实例 |
| `@pytest.fixture(scope='session')` QApplication | Qt 禁止多实例 | 会话级共享 qapp |

## Extension 测试

**修改 Extension 后必须手动测试：**
- Chrome 重启
- B站视频打开
- 视频切换
- 页面关闭
- 多轮循环

---

# AI 修改行为规范

## 修改前原则

**修改代码前必须先理解现有架构和数据流：**
- 阅读 [架构说明](#架构说明) 和 [关键架构约束](#关键架构约束)，确认修改点所在模块的职责边界
- 追踪相关模块的依赖关系（见 [模块依赖关系](#模块依赖关系)），确认无循环依赖
- 确认修改点所在的线程（GUI thread vs background thread），见 [线程模型](#线程模型)

**优先寻找已有状态、事件和机制解决问题：**
- 检查 [核心状态变量表](#核心状态变量) — `_wall_clock_start`、`_pending_clear` 能否表达新需求？
- 检查 [事件系统](#事件系统) — 能否利用已有 EventType 而非新增？
- 检查 [跨线程桥接模式](#线程模型) — 能否复用而非新建通信路径？

**优先采用最小修改方案，不主动扩大修改范围：**
- 一个 Issue 只改一个目标（见 [Git规范](#git规范)）
- 不混合多个 Issue 的修改
- 不进行大规模无关重构
- 修改前必须说明：**问题根因** → **涉及模块** → **修改方案** → **潜在影响**
- 遇到 Bug 先按 [Debug流程](#debug-流程) 分析，不要立即改代码

## 架构保护原则

**状态管理：**
- 不因为单个 bug 引入新的全局状态或重复状态
- 新增 flag/状态变量前，必须确认已有状态无法表达该需求
- 新增状态必须明确：谁创建、谁持有、谁销毁、初始值含义、重置时机
- 优先利用已有状态变量（如 `_wall_clock_start` 同时驱动窗口可见性和帧处理，无需新增 `_window_visible` flag）

**事件系统：**
- 不绕过现有 DataDispatcher 直接建立新的模块间通信路径
- 模块间通信一律通过 `dispatcher.publish()`，不直接调用对方内部方法
- 新增 EventType 需在 [events.py](python/events.py) 中定义为纯 @dataclass，不包含业务逻辑

**线程模型：**
- 不破坏现有双线程架构：
  - Background daemon thread — stdin 协议 + HTTP 请求 + dispatcher 发布
  - Qt GUI thread — QApplication + 窗口操作 + 渲染
- GUI 对象（Window, Renderer, TrayIcon）**只能在 GUI thread 操作**
- 跨线程通信优先使用已有的 `_pending_clear` flag 模式或 `pyqtSignal`

**模块边界：**
- Extension 不做弹幕业务逻辑，Python 不依赖浏览器 DOM（见 [架构说明](#架构说明)）
- 不修改现有模块间依赖方向：纯数据层 → 逻辑层 → 编排层
- 不引入循环依赖
- v0.2.x 是生命周期稳定性修复阶段，**不要引入 v0.3 功能**（播放同步、暂停同步、样式配置等）

## 测试要求

完整测试规范见 [测试规范](#测试规范)，核心要求：

- Python 代码修改 → 必须运行 `pytest`，**全部通过**
- Extension 代码修改 → 必须 Chrome 实机测试（重启、打开B站、视频切换、页面关闭、多轮循环）
- 不删除或降低已有测试覆盖
- 新增功能需同步新增测试

## 输出要求

完成修改后，必须报告：

| 项目 | 内容 |
|------|------|
| 修改文件列表 | 每个文件的路径和变更行数 |
| 修改原因 | 每个修改解决了什么问题 |
| 架构影响 | 是否改变了模块边界、线程模型、事件流 |
| 测试结果 | pytest 通过数 / 总数，Extension 手动测试结果 |
| 后续风险 | 残留状态、边缘情况、未覆盖场景 |

---

# Git 规范

原则：
- 小步提交
- 一个 Issue 一个目标
- commit 前必须完成测试
- commit message 说明功能变化

禁止：
- 大规模无关重构
- 混合多个 Issue 修改

---

# 模块依赖参考

## 当前版本: v0.2.x

## 模块依赖关系 (Python)

```
constants.py           ← 零依赖
events.py              ← 零依赖 (纯数据)
data_dispatcher.py     ← events.py
danmaku_parser.py      ← 零依赖 (纯解析)
danmaku_fetcher.py     ← constants.py
video_info_handler.py  ← constants.py
danmaku_handler.py     ← danmaku_fetcher, danmaku_parser, video_info_handler, events, data_dispatcher
overlay/danmaku_queue  ← danmaku_parser (DanmakuItem)
overlay/danmaku_renderer ← danmaku_parser, danmaku_queue (仅类型引用)
overlay/main_window.py ← danmaku_renderer
overlay/tray_icon.py   ← PyQt6 only
native_host.py         ← 所有模块 (编排入口)
```

无循环依赖。依赖方向: 纯数据层 → 逻辑层 → 编排层。
