# BiliDanmaku 项目状态

> 最后更新：2026-07-15
> 用途：上下文恢复。**Compact 后唯一上下文参考。** 仅记录对后续开发有价值的信息。

---

## 1. 当前版本与阶段

| 项目 | 状态 |
|------|------|
| 项目版本 | **v0.2.0-alpha** (已 tag) |
| 设计文档版本 | v0.4 ([docs/design.md](design.md)) |
| 开发阶段 | **Phase 2 alpha 已完成 → 等待实机端到端验证** |
| 当前目标 | 真实 B站视频端到端验证：BV → cid → 弹幕 → Python 输出 |
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
│   ├── content.js                 # Resolver Chain + 播放监听 + SPA检测
│   └── background.js              # Service Worker 消息中枢 + [Beta]重连
├── python/
│   ├── constants.py               # [v0.2.0-alpha] API 端点、HTTP 头、超时 集中常量
│   ├── native_host.py             # Native Messaging 协议 + 消息分发 + TeeStderr
│   ├── native_host.bat            # Native Host 启动器
│   ├── native_host.json           # Native Messaging 清单（扩展ID已填入）
│   ├── native_host.log            # 运行时日志（gitignored）
│   ├── test_native_host.py        # 集成协议测试（18/18 通过）
│   ├── danmaku_fetcher.py         # [v0.2.0-alpha] urllib HTTP 弹幕请求 → bytes
│   ├── danmaku_parser.py          # [v0.2.0-alpha] XML → DanmakuParseResult
│   ├── video_info_handler.py      # [v0.2.0-alpha] BV→cid API 补全 + dict 缓存
│   └── danmaku_handler.py         # [v0.2.0-alpha] 编排层 + 摘要生成
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
| 工作区 | 干净 |

### 1.3 Phase 完成情况

**Phase 1 (v0.1.x) — 全部完成 ✅**
- [x] Chrome Extension 自动检测 B站视频（Resolver Chain）
- [x] Native Messaging 通信验证（扩展 ↔ Python）
- [x] `native_host.py` 异常处理修复（单点故障不崩溃）
- [x] TeeStderr 文件日志（Chrome 进程调试）
- [x] 实机端到端验证通过（Chrome）

**Phase 2 alpha (v0.2.0-alpha) — 全部完成 ✅**
- [x] `python/constants.py` — 集中常量管理（API 端点、HTTP 头、超时）
- [x] `python/danmaku_parser.py` — XML 解析器 + DanmakuItem + DanmakuParseResult
- [x] `python/danmaku_fetcher.py` — urllib HTTP 请求，fetcher/parser 严格分离
- [x] `python/video_info_handler.py` — BV→cid API 补全 + 简单 dict 缓存
- [x] `python/danmaku_handler.py` — 编排层（cid补全→fetcher→parser→摘要生成）
- [x] `tests/test_danmaku_parser.py` — 23 单测（正常 + 边界 + 异常）
- [x] `tests/mock/sample_danmaku.xml` — 测试样本
- [x] `python/native_host.py` — 接入 danmaku_handler，`video_switch` 触发弹幕获取
- [x] `python/test_native_host.py` — 更新为 alpha 行为（18/18 通过）
- [x] 测试模式（$BILIDANMAKU_TEST_MODE=1）跳过真实 HTTP

**v0.2.0-alpha 用户调整全部落实：**
- [x] 零第三方依赖（`urllib.request` 替代 `requests`）
- [x] `constants.py` 集中管理常量
- [x] `DanmakuParseResult` 轻量结果对象（预留扩展字段）
- [x] video_info_handler 简单 dict 缓存（无 FIFO/LRU）
- [x] parser 单测含异常输入（畸形 XML / 空字节 / 垃圾字节）
- [x] danmaku_handler 生成摘要，native_host 不承担业务逻辑

---

## 2. 已确认的重要设计决策

### 2.1 整体架构

```
B站视频页 → content.js (Resolver Chain) → background.js
  → Native Messaging (stdin/stdout JSON) → Python native_host.py
    → danmaku_handler (编排)
      → video_info_handler (cid补全, PARTIAL only)
      → danmaku_fetcher (HTTP, 返回 bytes)
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
| Python 解析 | `xml.etree.ElementTree` (标准库) | 零外部依赖 |
| 桌面窗口 | PyQt6 | Phase 2.x 引入 |

### 2.3 关键设计原则（不可随意改变）

1. **自动识别是核心价值** — 绝不做"手动输入 BV 号"的功能。
2. **Resolver Chain 不强依赖 `__INITIAL_STATE__`** — 4 个 Resolver 链式降级（FULL→PARTIAL）。
3. **fetcher 与 parser 严格分离** — fetcher 返回 bytes，parser 负责解析。这是应对 B站 API/格式变化的隔离边界。
4. **零外部依赖（alpha 阶段）** — `urllib` + `xml.etree` 纯标准库。
5. **MV3 Service Worker 可能被挂起** — 复杂重连/心跳机制标为 [Beta]。
6. **单点故障不崩溃** — `native_host.py` 的 try/except 包裹单条消息处理。
7. **先做出来再拆模块** — 自然演进 > 提前设计。
8. **测试模式** — `BILIDANMAKU_TEST_MODE=1` 环境变量跳过真实 HTTP，集成测试专用。

### 2.4 演进路线

```
v0.1.2 (通信验证) → v0.2.0-alpha (弹幕链路,无PyQt) [当前]
  → 实机端到端验证 → v0.2.x (PyQt渲染) → v0.3 (同步+样式) → v1.0 (打包)
```

---

## 3. 已完成的工作

### 3.1 Phase 1 实机验证结果 (2026-07-14)

| 验证项 | 结果 | 说明 |
|--------|:--:|------|
| Native Host 注册表 | 通过 | Chrome 注册表写入成功 |
| 扩展加载 | 通过 | Chrome 开发者模式加载 `extension/` |
| Service Worker 连接 | 通过 | 日志显示 `Native Host 已连接` |
| video_switch 消息 | 通过 | `null → BV1W1Tp6xEhT`，Python 回复 `status: ok` |
| 重启后重连 | 通过 | 无 `Specified native messaging host not found` 错误 |
| TeeStderr 日志 | 通过 | `python/native_host.log` 正确捕获 Chrome 进程日志 |

### 3.2 v0.2.0-alpha 测试结果 (2026-07-15)

| 测试套件 | 结果 | 说明 |
|----------|:--:|------|
| `tests/test_danmaku_parser.py` | **23/23** | 正常解析(13) + 边界(6) + 异常(3) + 数据类(1) |
| `python/test_native_host.py` | **18/18** | FULL 弹幕获取 + PARTIAL 降级错误 + progress_update + 非法JSON韧性 |

### 3.3 已修复的 Bug

| Bug | 发现 | 修复 | 验证 |
|-----|------|------|------|
| `read_message()` JSON 解析异常导致进程崩溃 | Phase 1 测试非法数据触发 | `main()` 循环 try/except 覆盖 `read_message()` | v0.1.1, 17/17 通过 |
| Windows GBK 编码导致测试输出乱码 | `test_native_host.py` 首次运行 | 替换 emoji → ASCII `[PASS]`/`[FAIL]` + `sys.stdout.reconfigure(encoding='utf-8')` | 通过 |
| Python bytes 字面量含中文导致 SyntaxError | v0.2.0-alpha 开发中 | `_TEST_XML` 用 `.encode('utf-8')` 构建，测试用例用 `str.encode()` | 18/18 通过 |

### 3.4 v0.2.0-alpha 代码文件详情

| 文件 | 行数 | 关键内容 |
|------|:--:|------|
| `python/constants.py` | ~40 | `BILIBILI_API`(3端点), `HTTP_HEADERS`, `TIMEOUTS`, `MAX_MESSAGE_BYTES`, `CID_CACHE_MAX_SIZE` |
| `python/danmaku_parser.py` | ~110 | `DanmakuItem`(8字段), `DanmakuParseResult`(items/total/source/skipped + 预留), `parse_xml()` |
| `python/danmaku_fetcher.py` | ~60 | `fetch_danmaku_raw(cid, segment_index)` → bytes; 测试模式返回预置 XML |
| `python/video_info_handler.py` | ~70 | `fetch_video_info(bvid)` → `{cid, title, duration}`; dict 缓存; 测试模式抛 ValueError |
| `python/danmaku_handler.py` | ~120 | `handle_video_switch(bv, cid, title, resolver_level)` → `{success, summary, result, error}` |
| `python/native_host.py` | ~200 | `video_switch` 分发到 `danmaku_handler`; `progress_update` 保持无业务逻辑 |

---

## 4. 下一步：实机端到端验证

### 4.1 验证目标

使用**真实 B站视频**验证完整链路：

```
浏览器打开 B站视频 → Resolver Chain 提取 BV/cid
  → Native Messaging → native_host.py
  → danmaku_handler → fetcher → parser
  → stderr/log 输出弹幕内容
```

### 4.2 验证步骤

1. 打开 Chrome，加载 `extension/` 目录
2. 打开 `https://www.bilibili.com/video/BV1xx411c7mD`（或其他 B站视频）
3. 检查 `python/native_host.log` 中的弹幕输出
4. 抽样对比 B站播放器弹幕与 log 中的弹幕内容

### 4.3 期望结果

- log 中出现 `弹幕获取完成: N 条`
- 弹幕时间范围合理（0s ~ 视频时长）
- 弹幕内容与 B站播放器弹幕一致（抽样）
- PARTIAL Resolver 降级时自动补全 cid
- 视频切换时自动获取新视频弹幕

### 4.4 可能发现的问题（待验证）

| 风险 | 说明 |
|------|------|
| 游客限制 | B站弹幕 API 可能限制未登录用户的弹幕数量/内容 |
| API 变化 | dm.so 接口可能已调整 |
| cid 有效性 | FULL Resolver 提供的 cid 可能已过期 |
| 编码问题 | XML 中特殊字符可能导致解析跳过部分弹幕 |

---

## 5. 下一开发阶段：v0.2.x（PyQt 渲染）

### 5.1 目标

弹幕获取链路验证通过后，引入 PyQt6 透明窗口渲染弹幕。

### 5.2 需新建的文件

| # | 文件 | 职责 |
|---|------|------|
| 1 | `python/data_dispatcher.py` | 线程安全事件总线（多消费者：log + renderer） |
| 2 | `python/overlay/__init__.py` | 包标记 |
| 3 | `python/overlay/main_window.py` | 透明无边框置顶窗口 + 鼠标穿透 |
| 4 | `python/overlay/danmaku_queue.py` | 弹幕缓冲队列 + 时间排序 + 容量控制 |
| 5 | `python/overlay/danmaku_renderer.py` | QPainter 滚动弹幕 (v0.2 仅 mode=1) |
| 6 | `python/overlay/tray_icon.py` | 系统托盘 + 右键退出 |

### 5.3 需修改的文件

- `python/native_host.py` — 接入 data_dispatcher
- `python/danmaku_handler.py` — 通过 dispatcher 发布 DanmakuLoadedEvent
- `requirements.txt` — 添加 PyQt6

---

## 6. 当前阻塞任务（Blocking Issues）

**轻微阻塞：** 实机端到端验证未完成 — 需要用户手动操作 Chrome 并检查 log。

---

## 7. 用户约束与偏好

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
| **v0.2.0-alpha 零第三方依赖** | 用户明确要求（2026-07-15） | `urllib.request` + `xml.etree` 纯标准库 |
| **v0.2.0-alpha 暂不引入 PyQt** | 用户明确要求（2026-07-14） | 先验证弹幕数据链路，PyQt 在 alpha 验证通过后再加 |
| **danmaku_handler 生成摘要** | 用户明确要求（2026-07-15） | native_host.py 不承担业务逻辑 |
| **测试模式（环境变量）** | 用户明确要求（2026-07-15） | BILIDANMAKU_TEST_MODE=1 跳过真实 HTTP |

---

## 8. 已知问题与风险

| 问题/风险 | 状态 | 影响 | 应对 |
|-----------|------|------|------|
| MV3 Service Worker 可能被挂起 | 待验证 | Phase 1 稳定性 | [Beta] 重连机制已保留代码框架 |
| B站弹幕 API 游客限制 | **待实机验证** | 弹幕获取 | Cookie Provider 抽象已设计，当前用游客模式 |
| `window.__INITIAL_STATE__` 结构变化 | 长期风险 | content.js | Resolver Chain 已有 3 个降级 Resolver |
| B站 API 接口可能变化 | 长期风险 | danmaku_fetcher | 端点常量化 + fetcher/parser 分离 |
| 实机端到端验证未完成 | **当前待办** | v0.2.0-alpha 验收 | 需用户手动打开 Chrome 测试 |
| Native Host 注册路径含中文/空格 | Windows 常见问题 | 安装 | `native_host.json` 中 path 用正斜杠 |
| 未登录用户弹幕数据可能受限 | 长期风险 | 弹幕完整性 | Cookie Provider 预留 |
| ~~Python 控制台不可见~~ | ✅ 已解决 | — | TeeStderr 文件日志 |
| ~~read_message JSON 解析崩溃~~ | ✅ 已修复 | — | try/except 单消息保护 |
| ~~Windows GBK 编码乱码~~ | ✅ 已解决 | — | ASCII 标记 + UTF-8 reconfigure |
