# BiliDanmaku 项目状态

> 最后更新：2026-07-14
> 用途：上下文恢复。仅记录对后续开发有价值的信息。

---

## 1. 当前版本与阶段

| 项目 | 状态 |
|------|------|
| 项目版本 | **v0.1** (MVP Phase 1) |
| 设计文档版本 | v0.4 ([docs/design.md](design.md)) |
| 开发阶段 | **MVP Phase 1 已完成代码编写，待实机验证** |
| 目标 | Edge/Chrome 打开 B站视频 → Python 控制台打印结构化视频信息 |

**Phase 1 完成情况：**
- [x] `extension/manifest.json` — 已更新（host_permissions + content_scripts）
- [x] `extension/content.js` — 已创建（Resolver Chain + 播放监听 + SPA检测）
- [x] `extension/background.js` — 已重写（connectNative + 消息路由 + [Beta]重连）
- [x] `python/native_host.py` — 已重写（Native Messaging 协议 + 结构化打印 + try/except）
- [x] `docs/design.md` — 已保存
- [ ] **实机验证** — 注册 Native Host → 加载扩展 → 打开B站视频 → 确认 Python 收到消息

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

### 3.3 尚未验证

- [ ] Native Host 注册到 Windows 注册表
- [ ] 扩展加载到 Chrome/Edge
- [ ] 端到端消息链路（B站页面 → Python stderr）
- [ ] SPA 视频切换检测
- [ ] Resolver 降级行为

---

## 4. 下一步开发计划

### 4.1 当前最优先：Phase 1 实机验证

按 [design.md §10.7.5](design.md#1075-mvp-推荐调试流程) 执行：

1. Python 独立测试：用测试脚本验证 native_host.py 协议正确
2. 注册 Native Host：编写 `native_host.json`，写入注册表（Chrome + Edge）
3. 加载扩展：`chrome://extensions` → 开发者模式 → 加载 `extension/` 目录
4. 打开 B站视频，观察 Python stderr 输出
5. 验证视频切换、暂停/播放、进度拖动的消息更新

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

## 5. 用户约束与偏好

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

## 6. 已知问题与风险

| 问题/风险 | 状态 | 影响 | 应对 |
|-----------|------|------|------|
| MV3 Service Worker 可能被挂起导致 Native 连接断开 | 待验证 | Phase 1 稳定性 | [Beta] 重连机制已保留代码框架，实机实测后决定是否启用 |
| B站弹幕 API 游客限制 | 待验证 | Phase 2 弹幕获取 | Cookie Provider 抽象已设计，当前先用游客模式测试 |
| `window.__INITIAL_STATE__` 结构变化 | 长期风险 | content.js | Resolver Chain 已有 3 个降级 Resolver |
| B站 API 接口可能变化 | 长期风险 | danmaku_fetcher | 端点常量化 + fetcher/parser 分离 |
| Python 控制台不可见（Chrome 启动时 stderr 丢失） | 待验证 | 调试体验 | 建议 MVP 阶段手动启动 Python 观察输出；v0.2+ 写入日志文件 |
| Native Host 注册路径含中文/空格 | Windows 常见问题 | 安装 | `native_host.json` 中 path 需用双反斜杠或正斜杠 |
| 未登录用户弹幕数据可能受限 | 长期风险 | 弹幕完整性 | 设计阶段已预留 Cookie Provider，当前不作为阻塞项 |
