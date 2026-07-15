# BiliDanmaku 项目状态

> 最后更新：2026-07-15 (Step 2.2a 完成)
> 用途：上下文恢复。**Compact 后唯一上下文参考。** 仅记录对后续开发有价值的信息。

---

## 1. 当前版本与阶段

| 项目 | 状态 |
|------|------|
| 项目版本 | **v0.2.0-alpha** (已 tag) → **v0.2.x 开发中** |
| 设计文档版本 | v0.4 ([docs/design.md](design.md)) |
| 开发阶段 | **Phase 2.x — Step 2.2a (DanmakuQueue 弹幕缓冲队列) 已完成** |
| 当前目标 | 弹幕缓冲队列已完成 → 弹幕渲染引擎 |
| 下一目标 | Step 2.2b: danmaku_renderer |

### 1.1 项目目录结构

```
BiliDanmaku/
├── .git/                          # Git 仓库
├── .gitignore                     # 排除 __pycache__/*.log 等
├── CLAUDE.md                      # 项目指令（AI 上下文）
├── docs/
│   ├── design.md                  # 技术设计文档 v0.4
│   └── status.md                  # 项目状态快照（本文件）
├── extension/
│   ├── manifest.json              # Manifest V3 配置
│   ├── content.js                 # Resolver Chain + 播放监听 + SPA检测 + Cookie采集 [v0.2.0-alpha 更新]
│   └── background.js              # Service Worker 消息中枢 + Cookie透传 [v0.2.0-alpha 更新]
├── python/
│   ├── constants.py               # [v0.2.0-alpha] API 端点、HTTP 头(Cookie/Origin)、超时 集中常量
│   ├── events.py                   # [v0.2.x Step1] 事件类型枚举 + 数据类 (3 事件类型)
│   ├── data_dispatcher.py          # [v0.2.x Step1] 线程安全 Publish/Subscribe 事件总线
│   ├── overlay/                    # [v0.2.x Step2.1-2.2a] PyQt 桌面覆盖层
│   │   ├── __init__.py
│   │   ├── main_window.py          # 透明无边框置顶窗口 + 鼠标穿透
│   │   ├── tray_icon.py            # 系统托盘图标 + 右键退出菜单
│   │   └── danmaku_queue.py        # 弹幕缓冲队列 + 墙上时钟发射 + 线程安全
│   ├── native_host.py             # Native Messaging 协议 + 消息分发 + TeeStderr + Cookie提取
│   ├── native_host.bat            # Native Host 启动器
│   ├── native_host.json           # Native Messaging 清单（扩展ID已填入）
│   ├── native_host.log            # 运行时日志（gitignored）
│   ├── test_native_host.py        # 集成协议测试（18/18 通过）
│   ├── danmaku_fetcher.py         # [v0.2.0-alpha] urllib HTTP请求 + Cookie + Origin + deflate/gzip自动解压
│   ├── danmaku_parser.py          # [v0.2.0-alpha] XML → DanmakuParseResult
│   ├── video_info_handler.py      # [v0.2.0-alpha] BV→cid API 补全 + dict 缓存
│   └── danmaku_handler.py         # [v0.2.0-alpha] 编排层 + 摘要生成 + Cookie透传
└── tests/
    ├── __init__.py
    ├── test_danmaku_parser.py     # 解析器单测（23/23 通过）
    ├── test_dispatcher.py         # [v0.2.x Step1] dispatcher + events 单测（50/50 通过）
    ├── test_overlay.py            # [v0.2.x Step2.1] overlay 模块单测（37/37 通过）
    ├── test_danmaku_queue.py       # [v0.2.x Step2.2a] danmaku_queue 单测（50/50 通过）
    └── mock/
        └── sample_danmaku.xml      # 弹幕 XML 测试样本（6条, 3种mode）
```

### 1.2 Git 状态

| 项目 | 状态 |
|------|------|
| 当前分支 | `main` |
| 最新提交 | `6b06102` — Implement v0.2.0-alpha danmaku fetching and parsing pipeline |
| 标签 | `v0.1.0` → `v0.1.1` → `v0.1.2` → `v0.2.0-alpha` (当前) |
| 工作区 | **有未提交修改** — v0.2.0-alpha 实机验证修复 + v0.2.x Step 1 + Step 2.1 + Step 2.2a (见 §5) |

### 1.3 Phase 完成情况

**Phase 1 (v0.1.x) — 全部完成 ✅**
- [x] Chrome Extension 自动检测 B站视频（Resolver Chain）
- [x] Native Messaging 通信验证（扩展 ↔ Python）
- [x] `native_host.py` 异常处理修复（单点故障不崩溃）
- [x] TeeStderr 文件日志（Chrome 进程调试）
- [x] 实机端到端验证通过（Chrome）

**Phase 2 alpha (v0.2.0-alpha) — 全部完成 ✅，实机验证通过 ✅**
- [x] `python/constants.py` — 集中常量管理
- [x] `python/danmaku_parser.py` — XML 解析器
- [x] `python/danmaku_fetcher.py` — HTTP 请求 + Cookie + 自动解压
- [x] `python/video_info_handler.py` — BV→cid API 补全
- [x] `python/danmaku_handler.py` — 编排层 + 摘要生成
- [x] 测试模式（$BILIDANMAKU_TEST_MODE=1）
- [x] **实机端到端验证通过**（见 §3）

**Phase 2.x (v0.2.x) — Step 1 + Step 2.1 + Step 2.2a 已完成 ✅**
- [x] `python/events.py` — EventType 枚举 + 3 个事件数据类 (VideoSwitched, DanmakuLoaded, ProgressUpdated)
- [x] `python/data_dispatcher.py` — 线程安全 Publish/Subscribe 事件总线 (同步分发 + threading.Lock + 异常隔离)
- [x] `tests/test_dispatcher.py` — 50/50 通过 (事件数据类 + 订阅/发布/取消 + 线程安全 + 异常隔离 + 类型推断)
- [x] `python/overlay/__init__.py` — 包标记
- [x] `python/overlay/main_window.py` — 透明无边框置顶窗口 + 鼠标穿透 (WS_EX_TRANSPARENT) + 渲染回调占位
- [x] `python/overlay/tray_icon.py` — 系统托盘图标 + 程序化图标生成 + 右键退出菜单
- [x] `tests/test_overlay.py` — 37/37 通过 (窗口属性 + 标志 + 透明 + 几何 + 托盘菜单 + 图标生成 + 集成共存)
- [x] `python/overlay/danmaku_queue.py` — 弹幕缓冲队列 + 墙上时钟发射 + 线程安全 + 最大容量2000
- [x] `tests/test_danmaku_queue.py` — 50/50 通过 (构造 + load + tick + clear + 属性 + 线程安全 + 边界)
- [ ] Step 2.2b: danmaku_renderer (QPainter 滚动弹幕 + 多轨道管理 + QTimer 帧驱动)

---

## 2. 已确认的重要设计决策

### 2.1 整体架构

```
B站视频页 → content.js (Resolver Chain + Cookie采集)
  → background.js (消息路由 + Cookie透传)
  → Native Messaging (stdin/stdout JSON, 含cookies字段)
  → Python native_host.py (消息分发 + Cookie提取)
    → danmaku_handler (编排 + Cookie透传)
      → video_info_handler (cid补全, PARTIAL only)
      → danmaku_fetcher (HTTP + Cookie/Origin头 + deflate/gzip解压)
      → danmaku_parser (XML → DanmakuParseResult)
    → stderr/log 输出摘要

v0.2.x 已新增（尚未接入 native_host）:
  ┌─ data_dispatcher (事件总线) ─────────────────────────┐
  │  events.py + data_dispatcher.py                      │
  │  线程安全 Publish/Subscribe, 同步分发                  │
  └──────────────────────────────────────────────────────┘

  ┌─ PyQt Overlay 层 ────────────────────────────────────┐
  │  main_window.py   透明无边框置顶窗口 + 鼠标穿透        │
  │  tray_icon.py     系统托盘 + 右键退出菜单              │
  │  danmaku_queue.py 弹幕缓冲队列 + 墙上时钟发射          │
  │  [待做] danmaku_renderer.py  QPainter 渲染引擎        │
  └──────────────────────────────────────────────────────┘
```

**核心原则：扩展是"眼睛"（观察上报），Python 是"大脑和手"（决策执行）。**

**当前架构状态：** native_host.py → danmaku_handler（弹幕获取链路，已完成并实机验证）。data_dispatcher + overlay 层已实现但尚未与 native_host 串联（Step 3）。

### 2.2 技术选型

| 层 | 技术 | 备注 |
|----|------|------|
| 扩展 | Manifest V3, JS ES2020+ | Chrome/Edge 兼容 |
| 通信 | Chrome Native Messaging | 4字节 LE 长度前缀 + JSON |
| Python HTTP | `urllib.request` (标准库) | 零外部依赖 |
| Python 解压 | `gzip` / `zlib` (标准库) | deflate/gzip 自动解压 |
| Python 解析 | `xml.etree.ElementTree` (标准库) | 零外部依赖 |
| 桌面窗口 | PyQt6 | Phase 2.x 引入 |

### 2.3 关键设计原则（不可随意改变）

1. **自动识别是核心价值** — 绝不做"手动输入 BV 号"的功能。
2. **Resolver Chain 不强依赖 `__INITIAL_STATE__`** — 4 个 Resolver 链式降级，**BV 与 URL 交叉校验**防止 SPA 过渡期数据污染。
3. **fetcher 与 parser 严格分离** — fetcher 返回解压后的 XML bytes，parser 负责解析。压缩/解压是传输层问题，由 fetcher 处理。
4. **零外部依赖（alpha 阶段）** — `urllib` + `xml.etree` + `gzip` + `zlib` 纯标准库。
5. **MV3 Service Worker 可能被挂起** — 复杂重连/心跳机制标为 [Beta]。
6. **单点故障不崩溃** — `native_host.py` 的 try/except 包裹单条消息处理。
7. **先做出来再拆模块** — 自然演进 > 提前设计。
8. **测试模式** — `BILIDANMAKU_TEST_MODE=1` 环境变量跳过真实 HTTP。
9. **Cookie 由扩展采集** — 通过 Native Messaging 传递浏览器 `document.cookie`，保持新鲜度，无需手动配置。
10. **SPA 导航延迟解析** — 检测到 URL 变化后延迟 1s 再执行 Resolver Chain，等待 `__INITIAL_STATE__` 更新；PARTIAL 解析后 3s 自动重试获取更完整数据。
11. **事件总线同步分发** — [v0.2.x] `data_dispatcher` 在发布者线程同步调用订阅者。订阅者应快速返回（如推入内部 Queue），耗时操作（HTTP）由发布者在线程内先执行再发布结果。
12. **弹幕队列墙上时钟发射** — [v0.2.x] `danmaku_queue` 基于墙上时钟（`time.monotonic()` 差值）发射弹幕，不由视频播放器进度驱动。v0.3+ 再引入进度同步模式。
13. **弹幕队列索引指针去重** — [v0.2.x] 弹幕按 `time` 排序后通过 `_next_index` 指针递增发射，每条弹幕仅返回一次。O(k) 每帧新弹幕数，不重复扫描已发射项。
14. **队列线程安全独立锁** — [v0.2.x] `danmaku_queue` 持有独立 `threading.Lock`，与 `data_dispatcher` 的锁分离。两个模块可通过不同线程独立操作，无锁竞争。
15. **Overlay 零业务依赖** — [v0.2.x] overlay 层（main_window / tray_icon / danmaku_queue）均不依赖 events / data_dispatcher / native_host。各模块可独立测试、独立演进。

### 2.4 演进路线

```
v0.1.2 (通信验证) → v0.2.0-alpha (弹幕链路, 无PyQt) → 实机验证通过 ✅
  → v0.2.x (PyQt渲染, Step 1+2.1+2.2a 已完成) [当前]
  → v0.3 (同步+样式) → v1.0 (打包)
```

---

## 3. 实机端到端验证结果

### 3.1 Phase 1 实机验证 (2026-07-14)

| 验证项 | 结果 | 说明 |
|--------|:--:|------|
| Native Host 注册表 | ✅ 通过 | Chrome 注册表写入成功 |
| 扩展加载 | ✅ 通过 | Chrome 开发者模式加载 `extension/` |
| Service Worker 连接 | ✅ 通过 | 日志显示 `Native Host 已连接` |
| video_switch 消息 | ✅ 通过 | `null → BV1W1Tp6xEhT`，Python 回复 `status: ok` |
| 重启后重连 | ✅ 通过 | 无 `Specified native messaging host not found` 错误 |
| TeeStderr 日志 | ✅ 通过 | `python/native_host.log` 正确捕获 Chrome 进程日志 |

### 3.2 v0.2.0-alpha 实机验证 (2026-07-15) 🆕

| 验证项 | 结果 | 说明 |
|--------|:--:|------|
| BV → cid 补全 | ✅ 通过 | B站 API 返回正确 cid、title、duration |
| Cookie 采集与透传 | ✅ 通过 | `document.cookie` 经扩展→Native Messaging→fetcher 完整传递 |
| 弹幕 API 请求 | ✅ 通过 | HTTP 200, Content-Type: text/xml |
| deflate 解压 | ✅ 通过 | B站返回 raw deflate 压缩，fetcher 自动 `zlib.decompress(raw, -MAX_WBITS)` 解压 |
| XML 解析 | ✅ 通过 | 解压后 XML 被 parser 正确解析 |
| **弹幕获取数量** | **~1200 条** | 真实 B站视频（约 24 分钟），获取完整弹幕数据 |
| 摘要输出 | ✅ 通过 | 弹幕样本正确显示时间、模式(mode=1/4/5)、内容 |
| 视频切换 | ✅ 通过 | 切换视频后自动获取新视频弹幕 |
| SPA title 污染 | ✅ 已修复 | BV-URL 交叉校验 + 1s 延迟 + 3s 重试 |

### 3.3 v0.2.0-alpha 实机验证中发现并修复的问题 🆕

| # | 问题 | 根因 | 解决方案 |
|---|------|------|----------|
| 1 | **HTTP 412** | B站弹幕 API 风控拦截 — 需要 buvid3/buvid4 指纹 Cookie | 扩展采集 `document.cookie` → Native Messaging 传递 → fetcher 附加 `Cookie` + `Origin` 请求头 |
| 2 | **SPA title 污染** | SPA 导航时 `__INITIAL_STATE__` 未更新，`document.title` 残留旧数据 | (a) BV 与 URL 交叉校验 — 不匹配则跳过 Resolver (b) 导航后 1s 延迟再解析 (c) PARTIAL 解析后 3s 重试获取 FULL 数据 |
| 3 | **deflate 压缩** | B站返回 `Content-Encoding: deflate`，`urllib` 不自动解压 | fetcher 新增 `_decompress_response()` — raw deflate (`-MAX_WBITS`) + zlib fallback, gzip 一并支持 |

---

## 4. 测试结果

### 4.1 v0.2.x 自动化测试 (2026-07-15)

| 测试套件 | 结果 | 说明 |
|----------|:--:|------|
| `tests/test_danmaku_parser.py` | **23/23** | 正常解析(13) + 边界(6) + 异常(3) + 数据类(1) |
| `python/test_native_host.py` | **18/18** | FULL 弹幕获取 + PARTIAL 降级错误 + progress_update + 非法JSON韧性 |
| `tests/test_dispatcher.py` | **50/50** | 事件数据类(14) + 订阅(5) + 发布(7) + 取消(4) + 计数(4) + Reset(2) + 异常隔离(2) + 线程安全(3) + 类型推断(5) + 单例(2) + 模块级清理(2) |
| `tests/test_overlay.py` | **37/37** 🆕 | 窗口构造(4) + 标志(3) + 透明(2) + 几何(3) + render_area(2) + 渲染回调(3) + 鼠标穿透(2) + Win32常量(4) + 托盘构造(3) + 菜单(4) + 图标生成(4) + 集成共存(2) |
| `tests/test_danmaku_queue.py` | **50/50** 🆕 | 构造(5) + load(7) + tick(14) + clear(5) + 属性(6) + 线程安全(3) + 边界(10) |

### 4.2 已修复的 Bug

| Bug | 发现 | 修复 | 验证 |
|-----|------|------|------|
| `read_message()` JSON 解析异常导致进程崩溃 | Phase 1 测试 | `main()` 循环 try/except | v0.1.1, 17/17 |
| Windows GBK 编码导致测试输出乱码 | `test_native_host.py` 首次运行 | ASCII 标记 + `sys.stdout.reconfigure(encoding='utf-8')` | 通过 |
| Python bytes 字面量含中文导致 SyntaxError | v0.2.0-alpha 开发 | `_TEST_XML` 用 `.encode('utf-8')` | 18/18 |
| B站 API HTTP 412 风控 | v0.2.0-alpha 实机验证 | 扩展 Cookie 透传 + Origin 头 | 实机通过 |
| SPA 视频切换 title 数据污染 | v0.2.0-alpha 实机验证 | BV-URL 交叉校验 + 延迟解析 + 重试 | 实机通过 |
| Content-Encoding: deflate 压缩数据未解压 | v0.2.0-alpha 实机验证 | fetcher 新增 raw deflate + zlib + gzip 自动解压 | 实机通过 |

---

## 5. 当前未提交修改 🆕

以下文件在 v0.2.0-alpha 实机验证 + v0.2.x Step 1 + Step 2.1 + Step 2.2a 中有修改，尚未提交：

| 文件 | 修改内容 |
|------|----------|
| `docs/status.md` | 实机验证结果更新 + v0.2.x Step 1 状态记录（本文件） |
| `python/constants.py` | 新增 `Origin`, `Accept` 请求头 |
| `python/events.py` | **新建** — EventType 枚举 + 3 个事件数据类 |
| `python/data_dispatcher.py` | **新建** — 线程安全 Publish/Subscribe 事件总线 |
| `python/danmaku_fetcher.py` | Cookie 参数、412 诊断、deflate/gzip 自动解压、调试日志 |
| `python/danmaku_handler.py` | `handle_video_switch()` 新增 `cookie` 参数 |
| `python/native_host.py` | 从 payload 提取 `cookies` 传给 handler |
| `tests/test_dispatcher.py` | **新建** — dispatcher + events 单测（50/50 通过） |
| `python/overlay/__init__.py` | **新建** — PyQt Overlay 层包标记 |
| `python/overlay/main_window.py` | **新建** — 透明无边框置顶窗口 + 鼠标穿透 |
| `python/overlay/tray_icon.py` | **新建** — 系统托盘图标 + 右键退出菜单 |
| `tests/test_overlay.py` | **新建** — overlay 模块单测（37/37 通过） |
| `python/overlay/danmaku_queue.py` | **新建** — 弹幕缓冲队列 + 墙上时钟发射 + 线程安全 |
| `tests/test_danmaku_queue.py` | **新建** — danmaku_queue 单测（50/50 通过） |
| `extension/background.js` | `video_switch` 消息携带 `cookies` 字段 |
| `extension/content.js` | BV-URL 交叉校验、SPA 1s 延迟、PARTIAL 3s 重试、`document.cookie` 采集、增强日志 |

---

## 6. v0.2.x 已完成模块详解与下一步计划

### 6.1 Step 1 产出（已完成 ✅）

| 文件 | 行数 | 职责 |
|------|------|------|
| `python/events.py` | ~40 | 3 种 EventType + 3 个 @dataclass 事件数据类 |
| `python/data_dispatcher.py` | ~125 | 线程安全事件总线：subscribe / unsubscribe / publish / reset |
| `tests/test_dispatcher.py` | ~540 | 50 项单测覆盖：数据类 / 订阅 / 发布 / 取消 / 线程安全 / 异常隔离 / 类型推断 |

**关键设计决策：**
- **同步分发**：订阅者回调在发布者线程中执行（v0.2 简化方案），耗时操作不应在回调中执行
- **异常隔离**：单个订阅者崩溃静默捕获，不传播、不影响其他订阅者
- **事件类型推断**：通过事件数据类类名自动映射到 EventType 枚举（`DanmakuLoadedEvent` → `DANMAKU_LOADED`）
- **模块级单例**：`from data_dispatcher import dispatcher` 获取全局实例
- **零依赖**：纯 Python 标准库（`threading.Lock`），不依赖 PyQt

### 6.2 Step 2.1 产出（已完成 ✅）

| 文件 | 行数 | 职责 |
|------|------|------|
| `python/overlay/__init__.py` | ~12 | 包标记 + 模块说明 |
| `python/overlay/main_window.py` | ~175 | 透明无边框置顶窗口 + Win32 鼠标穿透 + 渲染回调占位接口 |
| `python/overlay/tray_icon.py` | ~115 | 系统托盘 + 程序化图标（粉色圆形"弹"字）+ 右键退出菜单 |
| `tests/test_overlay.py` | ~350 | 37 项单测覆盖：窗口属性 / 标志 / 透明 / 几何 / 托盘菜单 / 图标生成 |

**关键设计决策：**
- **延迟鼠标穿透**：在 `showEvent()` 中设置 `WS_EX_TRANSPARENT`（`winId()` 仅在 `show()` 后返回有效 HWND）
- **程序化图标**：QPainter 绘制，免外部 .png 依赖，v0.3+ 替换为资源文件
- **零业务依赖**：窗口和托盘均不依赖 events / data_dispatcher / danmaku 模块
- **当前状态**：native_host.py 尚未接入 Qt，dispatcher 尚未接入 overlay

### 6.3 Step 2.2a 产出（已完成 ✅）

| 文件 | 行数 | 职责 |
|------|------|------|
| `python/overlay/danmaku_queue.py` | ~150 | 弹幕缓冲队列 + 墙上时钟发射 + 线程安全 (threading.Lock) |
| `tests/test_danmaku_queue.py` | ~430 | 50 项单测覆盖：构造 / load / tick / clear / 属性 / 线程安全 / 边界 |

**关键设计决策：**
- **索引指针发射**：弹幕按 `time` 排序后通过 `_next_index` 指针递增发射，O(k) 其中 k 为每帧新弹幕数，不重复扫描已发射弹幕
- **墙上时钟**：`tick(elapsed)` 接收调用方计算的墙上时钟差值，队列不维护自己的计时器
- **隐式清空**：`load()` 替换全部弹幕并重置发射指针，适配视频切换场景
- **容量截断**：超过 `max_capacity` 时保留 time 最早的弹幕（排序后取前 N 条）
- **线程安全**：所有公开方法持有 `threading.Lock`，load/tick/clear 可在多线程并发调用
- **零业务依赖**：仅依赖 `danmaku_parser.DanmakuItem`（纯数据类），不依赖 PyQt / events / dispatcher

**API 摘要：**
| 方法 | 说明 |
|------|------|
| `load(items)` | 加载弹幕列表，清空旧弹幕，按 time 排序，容量截断 |
| `tick(elapsed)` | 返回 time ≤ elapsed 且未发射过的弹幕（按 time 升序） |
| `clear()` | 清空所有弹幕并重置发射状态 |
| `remaining` | 尚未发射的弹幕数量 |
| `total` | 队列弹幕总数 |
| `emitted_count` | 已发射弹幕数量 |
| `capacity` | 最大容量（只读） |

### 6.4 Step 2.2b 目标

创建弹幕渲染引擎，实现 QPainter 弹幕从队列到屏幕的绘制管线。

**需新建的文件：**

| # | 文件 | 职责 |
|---|------|------|
| 1 | `python/overlay/danmaku_renderer.py` | QPainter 滚动弹幕 + 多轨道管理 + QTimer 帧驱动 |

**Step 2.2b 不修改的文件：**
- `python/native_host.py`（Step 3 再重构）
- `python/data_dispatcher.py`（Step 3 再接入）
- `python/overlay/main_window.py`
- `python/overlay/danmaku_queue.py`

### 6.5 完整 v0.2.x 实施计划（共 5 步）

```
Step 1 ✅     Step 2.1 ✅    Step 2.2a ✅   Step 2.2b      Step 3           Step 4
──────▶       ──────▶        ──────▶        ──────▶        ──────▶          ──────▶
events +      PyQt Overlay   danmaku_       danmaku_       native_host      端到端串联
dispatcher    基础窗口层     queue           renderer       重构+集成         测试验证
```

| Step | 内容 | 新建 | 修改 |
|------|------|------|------|
| 1 | events + data_dispatcher | 2 文件 | 0 |
| 2.1 | PyQt Overlay 基础窗口层 | 3 文件 | 0 |
| 2.2a | danmaku_queue 缓冲队列 | 2 文件 | 0 |
| 2.2b | danmaku_renderer 渲染引擎 | 1 文件 | 0 |
| 3 | native_host 重构 + dispatcher 集成 | 0 | native_host.py, danmaku_handler.py (微量) |
| 4 | 端到端串联 + 实机验证 | 0 | 0 |

---

## 7. 阻塞任务（Blocking Issues）

**无阻塞。** 实机验证通过，可进入 v0.2.x 开发。

---

## 8. 用户约束与偏好

| 约束 | 来源 | 说明 |
|------|------|------|
| 自动识别必须纳入 MVP | 用户明确要求 | 手动输入 BV 号无用户价值 |
| Phase 1 不过度模块化 | 用户明确要求 | Python 端一个文件即可 |
| content.js 使用 Resolver Chain | 用户明确要求 | 不强依赖 `__INITIAL_STATE__` |
| MV3 SW 生命周期需考虑 | 用户明确要求 | 复杂重连暂标 [Beta] |
| Resolver 按信息完整度分级 | 用户明确要求 | FULL 优先，PARTIAL 降级 |
| 日志规范从 MVP 建立 | 用户明确要求 | Extension console 三级分层 |
| 桌面工具不崩溃 | 用户明确要求 | 单点异常 try/except |
| 先做出来再拆模块 | 用户偏好 | 自然演进 > 提前设计 |
| **v0.2.0-alpha 零第三方依赖** | 用户明确要求 | `urllib.request` + `xml.etree` 纯标准库 |
| **v0.2.0-alpha 暂不引入 PyQt** | 用户明确要求 | 先验证弹幕数据链路 |
| **danmaku_handler 生成摘要** | 用户明确要求 | native_host.py 不承担业务逻辑 |
| **fetcher/parser 严格分离** | 用户明确要求 | 压缩处理在 fetcher，parser 只接收 XML bytes |
| **Cookie 由扩展透传，不做独立 Provider** | 用户明确要求 (v0.2.0-alpha) | 保持简单，v0.3+ 再评估 |

---

## 9. 已知问题与风险

| 问题/风险 | 状态 | 影响 | 应对 |
|-----------|------|------|------|
| MV3 Service Worker 可能被挂起 | 待验证 | Phase 1 稳定性 | [Beta] 重连机制已保留代码框架 |
| B站弹幕 API 游客限制 | **已通过** | 弹幕获取 | Cookie 透传方案有效，游客模式可获取弹幕 |
| `window.__INITIAL_STATE__` 结构变化 | 长期风险 | content.js | Resolver Chain 已有 3 个降级 Resolver |
| B站 API 接口可能变化 | 长期风险 | danmaku_fetcher | 端点常量化 + fetcher/parser 分离 |
| B站响应压缩格式变化 | 低风险 | danmaku_fetcher | deflate raw/zlib + gzip 均支持，不支持时明确报错 |
| Native Host 注册路径含中文/空格 | Windows 常见问题 | 安装 | `native_host.json` 中 path 用正斜杠 |
| 未登录用户弹幕数据可能受限 | 低风险 | 弹幕完整性 | 当前游客模式已可获取 1200+ 条弹幕 |
| ~~Python 控制台不可见~~ | ✅ 已解决 | — | TeeStderr 文件日志 |
| ~~read_message JSON 解析崩溃~~ | ✅ 已修复 | — | try/except 单消息保护 |
| ~~Windows GBK 编码乱码~~ | ✅ 已解决 | — | ASCII 标记 + UTF-8 reconfigure |
| ~~HTTP 412 风控拦截~~ | ✅ 已解决 | — | Cookie 透传 + Origin 头 |
| ~~SPA title 数据污染~~ | ✅ 已解决 | — | BV-URL 交叉校验 + 延迟解析 |
| ~~deflate 压缩未解压~~ | ✅ 已解决 | — | fetcher 自动解压 |
