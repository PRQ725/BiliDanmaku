# BiliDanmaku 项目状态

> 最后更新：2026-07-15
> 用途：上下文恢复。**Compact 后唯一上下文参考。** 仅记录对后续开发有价值的信息。

---

## 1. 当前版本与阶段

| 项目 | 状态 |
|------|------|
| 项目版本 | **v0.2.0-alpha** (已 tag) |
| 设计文档版本 | v0.4 ([docs/design.md](design.md)) |
| 开发阶段 | **Phase 2 alpha 已完成 → 实机验证通过 → 准备进入 v0.2.x** |
| 当前目标 | 实机端到端验证 ✅ 已完成 |
| 下一目标 | v0.2.x（PyQt 透明窗口 + 弹幕滚动渲染） |

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
    ├── mock/
    │   └── sample_danmaku.xml      # 弹幕 XML 测试样本（6条, 3种mode）
    └── test_danmaku_parser.py     # 解析器单测（23/23 通过）
```

### 1.2 Git 状态

| 项目 | 状态 |
|------|------|
| 当前分支 | `main` |
| 最新提交 | `6b06102` — Implement v0.2.0-alpha danmaku fetching and parsing pipeline |
| 标签 | `v0.1.0` → `v0.1.1` → `v0.1.2` → `v0.2.0-alpha` (当前) |
| 工作区 | **有未提交修改** — v0.2.0-alpha 实机验证修复 (见 §5) |

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
```

**核心原则：扩展是"眼睛"（观察上报），Python 是"大脑和手"（决策执行）。**

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

### 2.4 演进路线

```
v0.1.2 (通信验证) → v0.2.0-alpha (弹幕链路, 无PyQt) → 实机验证通过 ✅ [当前]
  → v0.2.x (PyQt渲染) → v0.3 (同步+样式) → v1.0 (打包)
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

### 4.1 v0.2.0-alpha 自动化测试 (2026-07-15)

| 测试套件 | 结果 | 说明 |
|----------|:--:|------|
| `tests/test_danmaku_parser.py` | **23/23** | 正常解析(13) + 边界(6) + 异常(3) + 数据类(1) |
| `python/test_native_host.py` | **18/18** | FULL 弹幕获取 + PARTIAL 降级错误 + progress_update + 非法JSON韧性 |

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

以下文件在 v0.2.0-alpha 实机验证中有修改，尚未提交：

| 文件 | 修改内容 |
|------|----------|
| `docs/status.md` | 实机验证结果更新（本文件） |
| `python/constants.py` | 新增 `Origin`, `Accept` 请求头 |
| `python/danmaku_fetcher.py` | Cookie 参数、412 诊断、deflate/gzip 自动解压、调试日志 |
| `python/danmaku_handler.py` | `handle_video_switch()` 新增 `cookie` 参数 |
| `python/native_host.py` | 从 payload 提取 `cookies` 传给 handler |
| `extension/background.js` | `video_switch` 消息携带 `cookies` 字段 |
| `extension/content.js` | BV-URL 交叉校验、SPA 1s 延迟、PARTIAL 3s 重试、`document.cookie` 采集、增强日志 |

---

## 6. 下一步：v0.2.x（PyQt 渲染）

### 6.1 目标

引入 PyQt6 透明窗口渲染弹幕。弹幕获取链路已验证通过。

### 6.2 需新建的文件

| # | 文件 | 职责 |
|---|------|------|
| 1 | `python/data_dispatcher.py` | 线程安全事件总线（多消费者：log + renderer） |
| 2 | `python/overlay/__init__.py` | 包标记 |
| 3 | `python/overlay/main_window.py` | 透明无边框置顶窗口 + 鼠标穿透 |
| 4 | `python/overlay/danmaku_queue.py` | 弹幕缓冲队列 + 时间排序 + 容量控制 |
| 5 | `python/overlay/danmaku_renderer.py` | QPainter 滚动弹幕 (v0.2 仅 mode=1) |
| 6 | `python/overlay/tray_icon.py` | 系统托盘 + 右键退出 |

### 6.3 需修改的文件

- `python/native_host.py` — 接入 data_dispatcher
- `python/danmaku_handler.py` — 通过 dispatcher 发布 DanmakuLoadedEvent
- `requirements.txt` — 添加 PyQt6

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
