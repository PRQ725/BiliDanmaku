# BiliDanmaku 项目状态

> 最后更新：2026-07-14
> 用途：上下文恢复。仅记录对后续开发有价值的信息。

---

## 1. 当前版本与阶段

| 项目 | 状态 |
|------|------|
| 项目版本 | **v0.1** (MVP Phase 1) |
| 设计文档版本 | v0.4 ([docs/design.md](design.md)) |
| 开发阶段 | **MVP Phase 1 端到端验证通过，进入 Phase 2** |
| 目标 | Edge/Chrome 打开 B站视频 → Python 控制台打印结构化视频信息 ✅ |

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
│   ├── content.js                 # Resolver Chain + 播放监听 + SPA检测
│   └── background.js              # Service Worker 消息中枢 + [Beta]重连
└── python/
    ├── native_host.py             # Native Messaging 协议 + TeeStderr 文件日志
    ├── native_host.bat            # Native Host 启动器
    ├── native_host.json           # Native Messaging 清单（扩展ID已填入）
    └── test_native_host.py        # 独立协议测试（17/17 通过）
```

### 1.2 Git 状态

| 项目 | 状态 |
|------|------|
| 当前分支 | `main` |
| 最新提交 | `b1bdad2` — Complete MVP v0.1 implementation |
| 工作区 | 有未跟踪文件（Phase 1 验证准备文件） |
| 未跟踪文件 | `python/native_host.bat`, `python/native_host.json`, `python/test_native_host.py`, `.gitignore` |

### 1.3 Phase 1 完成情况
- [x] `extension/manifest.json` — 已更新
- [x] `extension/content.js` — Resolver Chain + 播放监听 + SPA 检测
- [x] `extension/background.js` — connectNative + 消息路由 + [Beta]重连
- [x] `python/native_host.py` — Native Messaging 协议 + 结构化打印 + 单点故障保护 + TeeStderr 文件日志
- [x] `python/test_native_host.py` — 协议独立测试（17/17 通过）
- [x] `python/native_host.json` — Native Host 清单（已注册 Chrome）
- [x] `python/native_host.bat` — Native Host 启动器
- [x] `.gitignore` — 排除运行时产物
- [x] `docs/design.md` — 技术设计文档 v0.4
- [x] **实机验证** — Chrome 端到端通信验证通过 ✅（2026-07-14）

---

## 2. 已确认的重要设计决策

### 2.1 整体架构

```
B站视频页 → content.js (Resolver Chain) → background.js
  → Native Messaging (stdin/stdout JSON) → Python native_host.py
```

**核心原则：扩展是"眼睛"（观察上报），Python 是"大脑和手"（决策执行）。**

### 2.2 技术选型

| 层 | 技术 | 备注 |
|----|------|------|
| 扩展 | Manifest V3, JS ES2020+ | Chrome/Edge 兼容 |
| 通信 | Chrome Native Messaging | 4字节 LE 长度前缀 + JSON |
| Python | 3.8+, 标准库 | MVP 零外部依赖 |
| 桌面窗口 | PyQt6 | Phase 2 引入 |

### 2.3 关键设计原则（不可随意改变）

1. **自动识别是核心价值** — 绝不做"手动输入 BV 号"的功能，那不是 MVP。
2. **Resolver Chain 不强依赖 `__INITIAL_STATE__`** — 4 个 Resolver 链式降级（FULL→PARTIAL），`__INITIAL_STATE__` 只是其中之一。
3. **MVP Python 端只有一个文件** — `native_host.py`，无 data_dispatcher、无 handler。Phase 2 有实际需求时再拆分。
4. **fetcher 与 parser 严格分离** — fetcher 返回 bytes，parser 负责解析。这是应对 B站 API/格式变化的隔离边界。
5. **MV3 Service Worker 可能被挂起** — 复杂重连/心跳机制标为 [Beta]，不作为 MVP 阻塞项。
6. **单点故障不崩溃** — native_host.py 的 try/except 包裹单条消息处理，不包裹整个循环。

### 2.4 演进路线

```
MVP v0.1 (当前) → v0.2 (弹幕获取+PyQt) → v0.3 (同步+样式) → v1.0 (打包)
```

---

## 3. 已完成的工作

### 3.1 文档

- [docs/design.md](design.md) — 完整技术设计文档 v0.4，包含：
  - MVP 定义与演进路线
  - 扩展/后端职责边界（含反模式）
  - 12 个未来模块的职责设计
  - 4 层数据格式规范（TS + Python dataclass）
  - Resolver Chain、PyQt 透明窗口、Native Messaging 关键技术方案
  - 变化风险矩阵 + 扩展预留设计（Cookie Provider、解析器策略模式等）
  - 4 个 Phase 的任务清单、测试策略、验收标准
  - Native Messaging 调试指南（注册、测试、排查）

### 3.2 代码文件

| 文件 | 说明 | 关键内容 |
|------|------|----------|
| `extension/manifest.json` | Manifest V3 配置 | host_permissions: `*://www.bilibili.com/*`, content_scripts matches: `/video/*` + `/bangumi/*` |
| `extension/content.js` | Resolver Chain + 播放监听 | InitialStateResolver(FULL), UrlRegexResolver(PARTIAL), MetaTagResolver(PARTIAL), VideoElementResolver(PARTIAL); PlaybackMonitor(事件+1s轮询); SpaNavigator(MutationObserver+URL检查) |
| `extension/background.js` | Service Worker 消息中枢 | connectNative + video_switch/progress_update 区分 + 1s限流 + [Beta]指数退避重连 |
| `python/native_host.py` | Native Messaging 协议入口 | read_message(4字节LE), handle_message(结构化打印), try/except单消息保护, 1MB上限 |

### 3.3 已修复的 Bug

| Bug | 发现 | 修复 | 验证 |
|-----|------|------|------|
| `read_message()` JSON 解析异常导致进程崩溃 | Step 1 测试 5（非法数据）触发 | `main()` 循环中 try/except 扩展覆盖 `read_message()` 调用 | `test_native_host.py` 17/17 通过 |

**详情：** 原代码只对 `handle_message()` 做了 try/except，但 `read_message()` 中的 `json.loads()` 可能抛出 `JSONDecodeError`，该异常未被捕获导致进程退出，违背"单点故障不崩溃"原则。

**修复前：**
```python
while True:
    msg = read_message()           # 异常 → 进程崩溃
    ...
    try:
        handle_message(msg)        # 仅保护了这里
    except Exception: ...
```

**修复后：**
```python
while True:
    try:
        msg = read_message()       # 异常 → 被捕获，进程继续
        ...
        handle_message(msg)
    except Exception as e:
        ...
        # Continue — next message may be fine
```

### 3.4 Phase 1 实机验证结果 (2026-07-14)

| 验证项 | 结果 | 说明 |
|--------|:--:|------|
| Native Host 注册表 | 通过 | Chrome 注册表写入成功，`connectNative()` 可找到 Host |
| 扩展加载 | 通过 | Chrome 开发者模式加载 `extension/` 目录 |
| Service Worker 连接 | 通过 | 日志显示 `Native Host 已连接` |
| video_switch 消息 | 通过 | `null → BV1W1Tp6xEhT`，Python 回复 `status: ok` |
| 重启后重连 | 通过 | 无 `Specified native messaging host not found` 错误 |
| TeeStderr 日志 | 通过 | `python/native_host.log` 正确捕获 Chrome 启动进程的日志 |

**验证发现的问题：**
- 手动启动 `python native_host.py` 看不到 Chrome 消息 — 正常行为：Chrome 连接的是它自己 spawn 的进程，不是手动启动的实例。解决方案：查看 `native_host.log` 文件获取 Chrome 进程日志。

---

## 4. 下一步开发计划

### 4.1 Phase 1 实机验证 ✅ 已完成

按 [design.md §10.7.5](design.md#1075-mvp-推荐调试流程) 执行：

1. [x] Python 独立测试：`test_native_host.py` 17/17 通过（含非法 JSON 不崩溃、TeeStderr 日志验证）
2. [x] 注册 Native Host：`native_host.json` → Chrome 注册表 → 连接成功
3. [x] 加载扩展：Chrome `chrome://extensions` → 加载 `extension/` → Service Worker 启动
4. [x] 端到端验证：Chrome 打开 B站视频 → Service Worker 日志显示 `Native Host 已连接` → Python 回复 `status: ok`
5. [x] 重启验证：重启 Chrome 后首次连接正常，无 `Specified native messaging host not found` 错误

**Phase 1 验证结论：Extension ↔ Native Messaging ↔ Python 通信链路正常工作。**

### 4.2 Phase 2 预览（验证通过后开始）

需新建的文件：
- `python/danmaku_fetcher.py` — 单分段 HTTP 请求（`dm.so?oid={cid}`）
- `python/danmaku_parser.py` — XML 解析 → `List[DanmakuItem]`
- `python/video_info_handler.py` — BV→cid API 调用（处理 PARTIAL Resolver 场景）
- `python/danmaku_handler.py` — 编排：cid → fetcher → parser → queue
- `python/data_dispatcher.py` — 线程安全事件总线
- `python/overlay/main_window.py` — PyQt 透明置顶窗口
- `python/overlay/danmaku_queue.py` — 弹幕时间排序缓冲
- `python/overlay/danmaku_renderer.py` — QPainter 滚动弹幕（仅 mode=1）
- `python/overlay/tray_icon.py` — 托盘图标 + 退出

**Phase 2 核心目标：** BV → cid → 单分段弹幕 → PyQt 渲染。不需要实现多分段并发、重试、Protobuf。

---

## 5. 当前阻塞任务（Blocking Issues）

> ~~Phase 1 实机验证~~ **已于 2026-07-14 完成。无阻塞项，已就绪进入 Phase 2。**

---

## 6. 用户约束与偏好

| 约束 | 来源 | 说明 |
|------|------|------|
| 自动识别必须纳入 MVP | 用户明确要求 | 手动输入 BV 号无用户价值，从一开始就是全自动 |
| Phase 1 不过度模块化 | 用户明确要求 | Python 端一个文件即可，功能增长再拆分 |
| content.js 使用 Resolver Chain | 用户明确要求 | 不强依赖 `__INITIAL_STATE__`，多策略提取 |
| MV3 SW 生命周期需考虑 | 用户明确要求 | 复杂重连暂标 [Beta]，不阻塞 MVP |
| Resolver 按信息完整度分级 | 用户明确要求 | FULL 优先，PARTIAL 降级，Python 补全 |
| 日志规范从 MVP 建立 | 用户明确要求 | Extension console 三级分层，Python v0.2+ 切 logging |
| 桌面工具不崩溃 | 用户明确要求 | 单点异常 try/except，不影响进程存活 |
| 先做出来再拆模块 | 用户偏好 | 自然演进 > 提前设计 |

---

## 7. 已知问题与风险

| 问题/风险 | 状态 | 影响 | 应对 |
|-----------|------|------|------|
| MV3 Service Worker 可能被挂起导致 Native 连接断开 | 待验证 | Phase 1 稳定性 | [Beta] 重连机制已保留代码框架，实机实测后决定是否启用 |
| B站弹幕 API 游客限制 | 待验证 | Phase 2 弹幕获取 | Cookie Provider 抽象已设计，当前先用游客模式测试 |
| `window.__INITIAL_STATE__` 结构变化 | 长期风险 | content.js | Resolver Chain 已有 3 个降级 Resolver |
| B站 API 接口可能变化 | 长期风险 | danmaku_fetcher | 端点常量化 + fetcher/parser 分离 |
| Python 控制台不可见（Chrome 启动时 stderr 丢失） | 待验证 | 调试体验 | 建议 MVP 阶段手动启动 Python 观察输出；v0.2+ 写入日志文件 |
| Native Host 注册路径含中文/空格 | Windows 常见问题 | 安装 | `native_host.json` 中 path 需用双反斜杠或正斜杠 |
| 未登录用户弹幕数据可能受限 | 长期风险 | 弹幕完整性 | 设计阶段已预留 Cookie Provider，当前不作为阻塞项 |
