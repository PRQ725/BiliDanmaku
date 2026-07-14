# BiliDanmaku 项目技术设计文档

> 版本：0.4
> 日期：2026-07-14
> 状态：设计阶段

---

## 目录

1. [项目概述](#1-项目概述)
2. [MVP 定义与演进路线](#2-mvp-定义与演进路线)
3. [整体架构](#3-整体架构)
4. [扩展与后端的职责边界](#4-扩展与后端的职责边界)
5. [模块设计](#5-模块设计)
6. [数据格式规范](#6-数据格式规范)
7. [关键技术方案](#7-关键技术方案)
8. [可维护性与扩展预留设计](#8-可维护性与扩展预留设计)
9. [开发阶段与验收标准](#9-开发阶段与验收标准)
10. [附录](#10-附录)

---

## 1. 项目概述

### 1.1 项目定位

BiliDanmaku 是一个桌面 B站弹幕助手。用户在 Edge 或 Chrome 浏览器观看 B站视频时，程序**自动识别**当前播放的视频，获取对应弹幕，并在桌面透明悬浮窗中滚动显示。

### 1.2 核心需求

| 编号 | 需求 | 优先级 | MVP |
|------|------|--------|-----|
| R1 | 自动识别浏览器中正在播放的 B站视频（无需手动输入 BV 号） | P0 | ✓ |
| R2 | 获取视频对应的弹幕数据 | P0 | ✗ |
| R3 | 在桌面透明置顶窗口中滚动显示弹幕 | P0 | ✗ |
| R4 | 支持 Edge 和 Chrome 浏览器 | P1 | ✓ |
| R5 | 弹幕显示与视频播放时间同步 | P1 | ✗ |
| R6 | 可配置弹幕样式（字体、大小、透明度、速度等） | P2 | ✗ |
| R7 | 支持弹幕开关、暂停/恢复 | P2 | ✗ |

### 1.3 技术栈

| 层次 | 技术 | 说明 |
|------|------|------|
| 浏览器扩展 | JavaScript (ES2020+), Manifest V3 | Chrome/Edge 兼容 |
| 通信层 | Chrome Native Messaging | 扩展 ↔ Python 进程间通信 |
| 后端服务 | Python 3.10+ | 弹幕获取、数据分发 |
| 桌面窗口 | PyQt6 | 透明置顶弹幕渲染 |
| 弹幕数据源 | B站 REST API (XML) | `api.bilibili.com` |

---

## 2. MVP 定义与演进路线

### 2.1 MVP 核心思想

**自动识别是项目核心价值。** MVP 必须证明"打开B站视频→程序自动感知"这条链路可行。手动输入 BV 号毫无用户价值，不纳入任何阶段。

MVP 的验收标准极简但关键：**Edge 打开 B站视频页 → Python 进程在控制台打印出结构化视频信息（BV号、cid、标题、播放进度）。**

### 2.2 MVP vs 完整版 范围对比

| 功能模块 | MVP (v0.1) | 完整版 (v1.0) |
|----------|-----------|--------------|
| 浏览器扩展 — 自动检测 BV号 | ✓ | ✓ |
| Native Messaging 通信 | ✓ | ✓ |
| Python 接收并打印视频信息 | ✓ | ✓（改为内部消费） |
| 弹幕获取（B站 API） | ✗ | ✓ |
| 弹幕解析（XML + Protobuf 预留） | ✗ | ✓ |
| PyQt 透明窗口 + 弹幕渲染 | ✗ | ✓ |
| 播放进度同步 | ✗ | ✓ |
| 弹幕样式配置 | ✗ | ✓ |
| 系统托盘 | ✗ | ✓ |
| 安装脚本 | ✗ | ✓ |

### 2.3 MVP 架构（简化版）

```
┌──────────────────────────────────────────────────────────────────┐
│                     Browser (Edge / Chrome)                       │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                   Extension (Manifest V3)                    │ │
│  │                                                              │ │
│  │  ┌──────────────────┐       ┌───────────────────────────┐   │ │
│  │  │   content.js      │ msg  │      background.js         │   │ │
│  │  │  (Resolver Chain) │─────▶│  (消息路由 + 长连接)       │   │ │
│  │  └──────────────────┘       └─────────────┬─────────────┘   │ │
│  └───────────────────────────────────────────┼─────────────────┘ │
│                                                │                   │
└────────────────────────────────────────────────┼───────────────────┘
                                                 │
                                    Native Messaging
                                                 │
┌────────────────────────────────────────────────┼───────────────────┐
│                       Python Backend            │                   │
│                                                  │                   │
│  ┌──────────────────────────────────────────────┼─────────────────┐ │
│  │                native_host.py                │                  │ │
│  │                                              │                  │ │
│  │  • Native Messaging 协议 (stdin/stdout)      │                  │ │
│  │  • 解析收到的 JSON 消息                      │                  │ │
│  │  • 打印结构化视频信息到控制台 (stderr)        │                  │ │
│  │  • 回复 {"status":"ok"}                      │                  │ │
│  └──────────────────────────────────────────────┘                  │ │
│                                                                    │ │
│  【Phase 2+ 才会增加：danmaku_fetcher, danmaku_parser,            │ │
│   overlay/, data_dispatcher 等模块】                               │ │
│                                                                    │ │
└────────────────────────────────────────────────────────────────────┘
```

MVP 阶段 Python 端**只有一个文件**：`native_host.py`。它的全部职责：
1. 从 stdin 读取 Native Messaging 协议消息
2. 解析 JSON
3. 打印到 stderr（控制台可见）
4. 回复 `{"status": "ok"}` 到 stdout
5. 循环直到连接断开

**不实现**任何弹幕获取、PyQt 窗口、事件总线、配置文件。

### 2.4 演进路线

```
MVP (v0.1)          v0.2                v0.3                v1.0
───────▶            ───────▶            ───────▶            ───────▶
自动检测BV号        弹幕获取            播放同步             安装打包
Native Messaging    PyQt透明窗口        弹幕样式配置         完整产品
Python打印消息      端到端串联          三种弹幕模式
                                       系统托盘完善
```

| 版本 | 核心交付物 | 新增能力 | Python 模块数 |
|------|-----------|----------|:----:|
| **MVP v0.1** | 扩展自动检测 + 消息到达 Python | 打开B站→Python感知 | 1 |
| **v0.2** | + 弹幕获取 + PyQt 渲染 | 自动显示弹幕 | ~8 |
| **v0.3** | + 播放同步 + 样式 + 托盘 | 完整体验 | ~10 |
| **v1.0** | + 安装脚本 + 文档 | 可分发 | ~10 |

---

## 3. 整体架构

### 3.1 完整版架构图 (v1.0)

```
┌──────────────────────────────────────────────────────────────────┐
│                     Browser (Chrome / Edge)                       │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                   Extension (Manifest V3)                    │ │
│  │                                                              │ │
│  │  ┌──────────────────┐       ┌───────────────────────────┐   │ │
│  │  │   content.js      │       │      background.js         │   │ │
│  │  │  (Resolver Chain) │ msg  │                            │   │ │
│  │  │                   │─────▶│ • 长连接管理               │   │ │
│  │  │ • URL 模式匹配     │       │ • 页面切换检测             │   │ │
│  │  │ • 多Resolver提取   │       │ • 消息路由与心跳          │   │ │
│  │  │ • 播放状态监听     │       │ • 重连与异常恢复          │   │ │
│  │  │ • 定时轮询同步     │       │                            │   │ │
│  │  └──────────────────┘       └─────────────┬─────────────┘   │ │
│  └───────────────────────────────────────────┼─────────────────┘ │
│                                                │                   │
└────────────────────────────────────────────────┼───────────────────┘
                                                 │
                                    Native Messaging
                                    (stdin/stdout, JSON,
                                     4-byte LE length prefix)
                                                 │
┌────────────────────────────────────────────────┼───────────────────┐
│                       Python Backend            │                   │
│                                                  │                   │
│  ┌──────────────────────────────────────────────┼─────────────────┐ │
│  │                native_host.py                │                  │ │
│  │                (消息入口 & 分发器)            │                  │ │
│  └───────────────────┬──────────────────────────┘                  │ │
│                      │                                              │ │
│         ┌────────────┼────────────┐                                │ │
│         │            │            │                                │ │
│  ┌──────┴──────┐ ┌───┴──────┐ ┌──┴──────────────┐                 │ │
│  │video_info   │ │danmaku   │ │command          │                 │ │
│  │_handler.py  │ │_handler  │ │_handler.py      │                 │ │
│  │ [v0.2+]     │ │.py       │ │ [v0.3+]         │                 │ │
│  │             │ │ [v0.2+]  │ │                 │                 │ │
│  │ BV号→cid    │ │ 弹幕拉取  │ │ 开关/暂停/样式  │                 │ │
│  │ 视频元数据   │ │ 解析/缓存 │ │ 设置/状态查询   │                 │ │
│  └──────┬──────┘ └───┬──────┘ └──┬──────────────┘                 │ │
│         │            │            │                                │ │
│  ┌──────┴────────────┴────────────┴───────────────────────────┐   │ │
│  │                    data_dispatcher.py [v0.2+]               │   │ │
│  │              内部事件总线 / 线程安全队列                      │   │ │
│  └──────────────────────────┬─────────────────────────────────┘   │ │
│                              │                                      │ │
│  ┌───────────────────────────┴─────────────────────────────────┐  │ │
│  │                    PyQt Overlay 层 [v0.2+]                  │  │ │
│  │                                                              │  │ │
│  │  ┌──────────────────┐  ┌──────────────────┐                 │  │ │
│  │  │ main_window.py   │  │ danmaku_queue.py │                 │  │ │
│  │  │                  │  │                  │                 │  │ │
│  │  │ • 透明无边框窗口  │  │ • 弹幕时间对齐   │                 │  │ │
│  │  │ • 置顶 + 鼠标穿透 │  │ • 多轨道调度     │                 │  │ │
│  │  │ • 全屏/区域可选   │  │ • 过期淘汰       │                 │  │ │
│  │  │ • 托盘图标控制    │  └────────┬─────────┘                 │  │ │
│  │  └────────┬─────────┘           │                            │  │ │
│  │           │                     │                            │  │ │
│  │  ┌────────┴─────────────────────┴──────────────────────┐    │  │ │
│  │  │              danmaku_renderer.py                     │    │  │ │
│  │  │                                                      │    │  │ │
│  │  │  • QPainter 文字绘制                                  │    │  │ │
│  │  │  • QTimer 帧驱动动画 (60fps)                          │    │  │ │
│  │  │  • 滚动 / 顶部 / 底部 三种模式                        │    │  │ │
│  │  │  • 多通道渲染                                        │    │  │ │
│  │  │  • 样式实时更新                                       │    │  │ │
│  │  └──────────────────────────────────────────────────────┘    │  │ │
│  └──────────────────────────────────────────────────────────────┘  │ │
└────────────────────────────────────────────────────────────────────┘
```

> [v0.2+] 标记表示该模块从 v0.2 开始引入，MVP 阶段不存在。

### 3.2 各阶段数据流

**MVP (v0.1)：**
```
B站视频页 → content.js (Resolver Chain提取信息) → background.js
  → Native Messaging → native_host.py (打印到stderr)
```

**v0.2：**
```
B站视频页 → content.js → background.js → native_host.py
  → data_dispatcher → video_info_handler (补全cid) + danmaku_handler
  → danmaku_fetcher (单分段请求) → danmaku_parser (XML→DanmakuItem)
  → danmaku_queue → danmaku_renderer → main_window (屏幕)

v0.2 第一版聚焦: BV → cid → 单分段弹幕 → 渲染
高级特性(多分段并发/重试/Protobuf)为后续迭代
```

**v0.3+：**
```
同上 + progress_update → danmaku_queue (精确同步)
       + command → command_handler → 样式/开关控制
```

---

## 4. 扩展与后端的职责边界

### 4.1 核心原则

> **浏览器扩展是"眼睛"，Python 后端是"大脑和手"。**
>
> 扩展只负责**观察和上报**（看视频、报状态），不做任何业务逻辑。
> Python 负责**所有决策和执行**（解析弹幕、管理队列、渲染画面）。

### 4.2 职责划分表

| 职责 | 浏览器扩展 | Python 后端 | 说明 |
|------|:---:|:---:|------|
| 检测用户是否在 B站视频页 | ● | ○ | 扩展通过 URL 匹配和 DOM 检测 |
| 提取 BV 号、cid | ● | ○ | Resolver Chain 多策略提取 |
| 监听播放进度 (currentTime) | ● | ○ | 每秒轮询 `<video>.currentTime` |
| 监听播放状态 (播放/暂停) | ● | ○ | 监听 `<video>` 的 play/pause 事件 |
| 消息传输（扩展→Python） | ● | ● | 扩展发送，Python 接收（各一半） |
| 连接管理与重连 | ● | ○ | 扩展负责发起连接和断线重连 |
| BV→cid 验证与查询 | ○ | ● | 通过 B站 API 确认 cid 有效性 |
| 弹幕数据获取（HTTP 请求） | ○ | ● | 调用 B站弹幕 API |
| 弹幕解析（XML/Protobuf） | ○ | ● | 纯数据处理 |
| 弹幕缓存与去重 | ○ | ● | 内存管理 |
| 弹幕时间排序与发射调度 | ○ | ● | 核心业务逻辑 |
| 桌面窗口创建与管理 | ○ | ● | PyQt 负责 |
| 弹幕渲染与动画 | ○ | ● | QPainter 绘制 |
| 弹幕样式管理 | ○ | ● | 配置读取和应用 |
| 用户设置（样式、开关） | ○ | ● | 通过托盘菜单或配置文件 |
| 错误处理与日志 | ● | ● | 各自独立处理自身错误 |

> ● = 主要负责 &nbsp;&nbsp; ○ = 不参与

### 4.3 接口契约

扩展与 Python 之间通过 Native Messaging 交换 JSON 消息。这个接口是两者的**唯一耦合点**。

**契约原则：**
1. **向前兼容**：新增字段不得破坏旧版 Python 后端的解析
2. **最小信息**：扩展只传原始数据，不做加工（例如传 `currentTime: 123.45`，不传 "弹幕应该发射到第N条"）
3. **无状态依赖**：每条消息自描述，Python 不依赖扩展记住之前的状态
4. **版本标识**：消息中包含 `protocolVersion`，Python 据此做兼容处理

### 4.4 边界反模式（明确禁止）

- ❌ 扩展**不应**缓存弹幕数据或做任何弹幕相关计算
- ❌ 扩展**不应**知道 PyQt 窗口是否存在（不关心渲染状态）
- ❌ Python **不应**尝试通过 Native Messaging 反向控制扩展
- ❌ Python **不应**包含任何 DOM 操作或浏览器相关逻辑

---

## 5. 模块设计

### 5.1 项目目录结构

```
BiliDanmaku/
├── docs/
│   └── design.md                    # 本设计文档
│
├── extension/                       # 浏览器扩展 (Manifest V3) [MVP]
│   ├── manifest.json                # 扩展清单
│   ├── background.js                # Service Worker — 消息中枢
│   └── content.js                   # Content Script — Resolver Chain 视频信息提取
│
├── python/                          # Python 后端
│   ├── native_host.py               # [MVP] Native Messaging 协议 + 消息打印
│   ├── danmaku_fetcher.py           # [v0.2+] B站弹幕API调用
│   ├── danmaku_parser.py            # [v0.2+] 弹幕数据解析
│   ├── video_info_handler.py        # [v0.2+] 视频信息处理 (BV→cid)
│   ├── danmaku_handler.py           # [v0.2+] 弹幕获取编排
│   ├── data_dispatcher.py           # [v0.2+] 内部事件总线
│   ├── command_handler.py           # [v0.3+] 用户指令处理
│   ├── config.py                    # [v0.3+] 配置管理
│   │
│   └── overlay/                     # PyQt 桌面覆盖层 [v0.2+]
│       ├── __init__.py
│       ├── main_window.py           # 主窗口 (透明、置顶、无边框)
│       ├── danmaku_queue.py         # 弹幕缓冲队列
│       ├── danmaku_renderer.py      # 弹幕渲染引擎
│       └── tray_icon.py             # 系统托盘图标
│
├── resources/                       # [v0.3+]
│   └── icon.png
│
├── tests/                           # [从 MVP 开始]
│   ├── test_danmaku_parser.py       # [v0.2+]
│   ├── test_danmaku_fetcher.py      # [v0.2+]
│   └── mock/
│       └── sample_danmaku.xml       # [v0.2+]
│
├── native_host.json                 # [MVP] Native Host 注册清单模板
├── install.bat                      # [v1.0]
├── requirements.txt                 # [MVP 仅需空文件, v0.2+ 添加依赖]
└── README.md                        # [v1.0]
```

> **[MVP]** = 第一阶段即创建 &nbsp;|&nbsp; **[v0.2+]** = 第二阶段引入 &nbsp;|&nbsp; **[v0.3+]** = 第三阶段引入

### 5.2 MVP 阶段模块（仅3个文件）

#### 5.2.1 content.js — Resolver Chain 视频信息提取

content.js 的核心设计是一个**可扩展的 Resolver Chain**（解析器链）。每个 Resolver 尝试从不同来源提取视频信息，链式调用。

**设计原则：**
1. **不依赖单一数据源。** `window.__INITIAL_STATE__` 只是链中的一个 Resolver。
2. **优先选择信息完整的 Resolver。** 每个 Resolver 返回不同完整度的信息，优先使用能提供 bv+cid+title+duration 的 Resolver，降级方案（仅有 bv）由 Python 端补全缺失字段。

**Resolver 能力等级：**

| 等级 | 字段 | 示例 Resolver | 说明 |
|------|------|---------------|------|
| **FULL** | bv + cid + title + duration | InitialStateResolver | 一次获取全部信息，无需 Python 补全 |
| **PARTIAL** | bv + title（cid=null, duration=null） | UrlRegexResolver, MetaTagResolver, VideoElementResolver | 只有 BV 号，cid/duration 需要 Python 调用 B站 API 补全 |

```javascript
// content.js — Resolver Chain 架构

/**
 * Resolver 接口约定：
 * - name: 唯一标识，用于日志
 * - level: "FULL" | "PARTIAL" — 信息完整度
 * - resolve(): 返回 {bv, cid, title, duration} | null
 *   其中 cid/duration 可为 null（PARTIAL 级别）
 * - 抛出异常时自动跳到下一个 Resolver
 */

class VideoInfoResolverChain {
    constructor() {
        // 按信息完整度排序：FULL 在前，PARTIAL 在后
        this.resolvers = [
            new InitialStateResolver(),     // 优先级1: FULL  — __INITIAL_STATE__
            new UrlRegexResolver(),         // 优先级2: PARTIAL — URL 正则
            new MetaTagResolver(),          // 优先级3: PARTIAL — <meta> 标签
            new VideoElementResolver(),     // 优先级4: PARTIAL — <video> 元素
        ];
    }

    resolve() {
        for (const resolver of this.resolvers) {
            try {
                const result = resolver.resolve();
                // 成功标准：至少提取到 bv，且不出异常
                if (result && result.bv) {
                    console.log(
                        `[BiliDanmaku] Resolver: ${resolver.name} ✓ ` +
                        `(level=${resolver.level}, cid=${result.cid ?? 'null'})`
                    );
                    // 附带 resolver 元信息，供 Python 判断是否需要补全
                    result._resolver = resolver.name;
                    result._level = resolver.level;
                    return result;
                }
            } catch (e) {
                console.warn(`[BiliDanmaku] Resolver ${resolver.name} 失败:`, e.message);
            }
        }
        console.error('[BiliDanmaku] 所有 Resolver 均失败');
        return null;
    }
}

// ─── 各 Resolver 实现 ───

class InitialStateResolver {
    name = 'InitialState';
    level = 'FULL';  // 能提供完整信息
    resolve() {
        const state = window.__INITIAL_STATE__;
        if (!state?.videoData) return null;
        return {
            bv: state.videoData.bvid,
            cid: state.videoData.cid,
            title: state.videoData.title,
            duration: state.videoData.duration,
        };
    }
}

class UrlRegexResolver {
    name = 'UrlRegex';
    level = 'PARTIAL';  // 仅 BV号，cid/duration 需 Python 补全
    resolve() {
        const match = location.href.match(/\/video\/(BV[a-zA-Z0-9]+)/);
        if (!match) return null;
        return { bv: match[1], cid: null, title: document.title, duration: null };
    }
}

class MetaTagResolver {
    name = 'MetaTag';
    level = 'PARTIAL';
    resolve() {
        const metaBv = document.querySelector('meta[itemprop="url"]')
            ?.getAttribute('content')?.match(/BV[a-zA-Z0-9]+/);
        if (!metaBv) return null;
        return { bv: metaBv[0], cid: null, title: document.title, duration: null };
    }
}

class VideoElementResolver {
    name = 'VideoElement';
    level = 'PARTIAL';
    resolve() {
        const video = document.querySelector('video');
        const bvMatch = (video?.src || '').match(/BV[a-zA-Z0-9]+/)
            || location.href.match(/\/video\/(BV[a-zA-Z0-9]+)/);
        if (!bvMatch) return null;
        return { bv: bvMatch[1], cid: null, title: document.title,
                 duration: video?.duration || null };
    }
}
```

**Python 端补全逻辑（当收到 PARTIAL 级别消息时）：**

```
native_host.py 收到 video_switch 消息
  → 若 cid != null → 直接使用（FULL level，无需额外请求）
  → 若 cid == null → 调用 B站 API: /x/web-interface/view?bvid={bv}
    → 获取 cid, duration 等完整信息
    → 补全后再进行后续弹幕获取
```

> 这个补全逻辑在 MVP 阶段暂不需要（MVP 只打印消息）。Phase 2 中由 `video_info_handler.py` 负责实现。

**扩展新 Resolver 的方式：** 实现 `{ name, level, resolve() }` 接口，在 Chain 构造函数中追加到合适位置（FULL 在前，PARTIAL 在后）。

**播放状态监听（Resolver 之外的独立职责）：**

| 项目 | 说明 |
|------|------|
| **触发条件** | Resolver Chain 成功提取视频信息后启动 |
| **核心职责** | 轮询 `<video>.currentTime` / `.paused`，监听 play/pause/seeked 事件 |
| **运行方式** | `setInterval` 定时轮询 (1s) + 事件监听 |
| **输出** | 通过 `chrome.runtime.sendMessage()` 向 background.js 发送 `{type, bv, cid, progress, isPlaying, ...}` |

#### 5.2.2 background.js — 消息中枢

| 项目 | 说明 |
|------|------|
| **核心职责** | 建立 Native Messaging 连接，将 content.js 消息转发给 Python |
| **MVP 范围** | 基础 `connectNative()` + 消息转发 + Console 日志。复杂重连/心跳机制**保留设计但不作为 MVP 验收项**（见 §7.5.1 关于 SW 生命周期的讨论） |
| **输入** | 来自 content.js 的视频信息消息 |
| **输出** | 通过 Native Messaging 转发给 Python |

**MVP 阶段的消息处理逻辑：**
```
Extension 启动 / SW 被唤醒
  → connectNative("com.bili.danmaku")
  → 连接成功: 开始监听 content.js 消息
  → 连接失败: console.error 记录错误

content.js 消息到达
  → 若与上一次 bv 不同 → 发送 video_switch 消息
  → 若相同 → 发送 progress_update 消息 (限流: 最多1次/s)

Python 回复的消息 → console.log 记录（MVP阶段不做处理）

连接断开 (onDisconnect)
  → console.warn 记录断开信息
  → 【Beta】尝试重连 (1s→2s→4s→8s, max 30s)
  → 重连成功 → 继续工作
  → 重连失败 → 等待下一次 SW 唤醒时重新 connectNative()
```

#### 5.2.3 native_host.py — MVP 唯一 Python 模块

| 项目 | 说明 |
|------|------|
| **核心职责** | 接收 Native Messaging 消息，打印到控制台，回复 ack |
| **输入** | stdin (4字节 LE 长度前缀 + JSON) |
| **输出** | stdout (ack 消息)；stderr (人类可读日志) |

**MVP 代码结构：**
```python
# native_host.py — MVP 阶段，单一文件，无外部依赖
import sys
import json
import struct

def read_message():
    """从 stdin 读取一条 Native Messaging 消息"""
    raw_len = sys.stdin.buffer.read(4)
    if not raw_len:
        return None
    msg_len = struct.unpack('<I', raw_len)[0]
    if msg_len > 1024 * 1024:  # 1MB 上限保护
        raise ValueError(f"消息过大: {msg_len} bytes")
    return json.loads(sys.stdin.buffer.read(msg_len).decode('utf-8'))

def send_message(msg):
    """向 stdout 写入一条 Native Messaging 消息"""
    data = json.dumps(msg, ensure_ascii=False).encode('utf-8')
    sys.stdout.buffer.write(struct.pack('<I', len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()

def handle_message(msg):
    """处理单条消息（MVP: 打印到 stderr + 回复 ok）"""
    msg_type = msg.get('type', 'unknown')
    payload = msg.get('payload', {})
    print(f"[BiliDanmaku] 收到消息 type={msg_type}", file=sys.stderr)
    print(f"  BV: {payload.get('bv')}", file=sys.stderr)
    print(f"  CID: {payload.get('cid')}", file=sys.stderr)
    print(f"  标题: {payload.get('title')}", file=sys.stderr)
    print(f"  时长: {payload.get('duration')}s", file=sys.stderr)
    print(f"  进度: {payload.get('progress')}s", file=sys.stderr)
    print(f"  播放中: {payload.get('isPlaying')}", file=sys.stderr)
    # 若收到 PARTIAL 级 Resolver 的结果（cid=null），MVP 阶段仅标记
    if payload.get('cid') is None:
        print(f"  ⚠ cid 为空, v0.2+ 将由 video_info_handler 补全", file=sys.stderr)

def main():
    print("[BiliDanmaku] Native Host 已启动", file=sys.stderr)
    while True:
        msg = read_message()
        if msg is None:
            print("[BiliDanmaku] 连接断开, 退出", file=sys.stderr)
            break
        try:
            handle_message(msg)
            send_message({"status": "ok"})
        except Exception as e:
            print(f"[BiliDanmaku] 消息处理异常: {e}", file=sys.stderr)
            # 不退出循环——下一条消息可能正常

if __name__ == '__main__':
    main()
```

> **设计要点：**
> - MVP 阶段故意不引入 `data_dispatcher`、`video_info_handler` 等模块。所有逻辑在一个文件中。
> - `handle_message` 使用独立的 try/except——单条消息失败不影响进程存活。
> - `print(file=sys.stderr)` 用于 MVP 快速验证。v0.2+ 切换到 `logging` 模块。
> - Phase 2 需要弹幕获取和 PyQt 渲染时，再自然拆分——有实际需求驱动的拆分比提前设计更加合理。

### 5.3 v0.2+ 阶段新增模块

以下模块在 v0.2 引入，此时 `native_host.py` 应将消息分发职责移交给 `data_dispatcher`。

#### 5.3.1 video_info_handler.py [v0.2+]

| 项目 | 说明 |
|------|------|
| **核心职责** | 验证 BV 号有效性，确认 cid，获取视频元数据 |
| **API 调用** | `https://api.bilibili.com/x/web-interface/view?bvid={bv}` |
| **缓存策略** | cid 映射缓存于内存 dict，LRU 淘汰（最大 20 条） |
| **输出** | `CidConfirmedEvent` → data_dispatcher |

#### 5.3.2 danmaku_handler.py [v0.2+]

| 项目 | 说明 |
|------|------|
| **核心职责** | 编排弹幕获取流程：分片请求、解析、注入队列 |
| **输入** | `CidConfirmed` 事件 |
| **输出** | 结构化弹幕列表 → danmaku_queue |

#### 5.3.3 danmaku_fetcher.py [v0.2+]

| 项目 | 说明 |
|------|------|
| **核心职责** | 封装 B站弹幕 API 的 HTTP 请求。**与 `danmaku_parser.py` 严格分离**：fetcher 只负责获取原始响应（bytes），parser 负责解析 |
| **接口** | `GET https://api.bilibili.com/x/v1/dm/list.so?oid={cid}` |
| **响应格式** | XML (UTF-8) |
| **v0.2 范围** | 单分段请求（`segment_index=1`），验证基本链路。**暂不实现**分片并发、Protobuf 兼容 |
| **超时** | 连接超时 5s，读取超时 10s |

**B站弹幕接口风险说明：**

| 风险 | 说明 | 应对 |
|------|------|------|
| 游客限制 | 当前 B站弹幕 API 无需登录。但未来可能限制未登录用户的弹幕可见数量或内容 | 通过 Cookie Provider 抽象预留登录注入点（见 §8.4） |
| 接口变化 | B站可能调整 API 路径、参数名或响应格式 | `danmaku_fetcher` 独立封装，变更时只改此模块。API 端点通过常量定义（见 §8.6） |
| 分片机制变化 | B站可能调整分片大小（当前约6分钟/段）或分片索引方式 | 先实现单分段验证链路，分段逻辑确认后再做并发 |
| 弹幕格式升级 | XML → Protobuf（`seg.so` 接口已存在） | `danmaku_parser` 使用策略模式，fetcher 根据 Content-Type 选择解析器（见 §8.3） |

**v0.2 第一版实现目标（核心链路验证）：**

```
BV → cid → dm.so?oid={cid} → XML bytes → parser → List[DanmakuItem] → 渲染
```

优先实现上述**单分段全链路**，确认能跑通后再逐步添加：
- 多分段并发请求
- 重试策略
- Protobuf 格式支持
- 弹幕去重

**v0.2 中的 fetcher 简化实现：**
```python
# danmaku_fetcher.py — v0.2 第一版，聚焦基本链路
import requests

BILIBILI_DANMAKU_URL = 'https://api.bilibili.com/x/v1/dm/list.so'

def fetch_danmaku_raw(cid: int, segment_index: int = 1) -> bytes:
    """获取弹幕原始 XML 响应。v0.2 只请求单个分段。"""
    resp = requests.get(
        BILIBILI_DANMAKU_URL,
        params={'oid': cid, 'segment_index': segment_index},
        headers={
            'User-Agent': 'Mozilla/5.0 ...',
            'Referer': 'https://www.bilibili.com/',
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.content  # bytes, 由 parser 负责解析
```

> **注意：** 分片并发、重试策略、Protobuf 等高级特性保留设计文档，但**不作为 v0.2 必须验收项**。v0.2 的核心目标是"打开 B站 → 弹幕出现在桌面"，不是"弹幕获取性能最优"。

#### 5.3.4 danmaku_parser.py [v0.2+]

| 项目 | 说明 |
|------|------|
| **核心职责** | 将 B站弹幕 XML 解析为 `List[DanmakuItem]` |

```python
@dataclass
class DanmakuItem:
    time: float          # 弹幕出现时间 (秒)
    content: str         # 弹幕文本内容
    mode: int            # 1=滚动, 4=底部, 5=顶部
    font_size: int       # 字号 (18/25/36)
    color: int           # RGB 颜色值 (十进制)
    timestamp: int       # Unix 发送时间戳
    danmaku_id: int      # 弹幕数据库 ID (去重用)
    pool: int            # 0=普通池, 1=字幕池
```

**XML `p` 属性解析规则（逗号分隔）：**

| 索引 | 字段 | 说明 |
|------|------|------|
| 0 | time | 弹幕出现时间 (秒) |
| 1 | mode | 1=滚动, 4=底部, 5=顶部 |
| 2 | font_size | 字号 |
| 3 | color | 十进制颜色值 |
| 4 | timestamp | Unix 发送时间 |
| 5 | pool | 弹幕池 |
| 6 | user_id | 用户ID hash |
| 7 | danmaku_id | 弹幕数据库 rowID |

#### 5.3.5 data_dispatcher.py [v0.2+]

| 项目 | 说明 |
|------|------|
| **核心职责** | 解耦各 Python 模块，提供发布-订阅消息机制 |
| **实现方案** | 基于 `queue.Queue` 的线程安全消息队列 |

#### 5.3.6 PyQt Overlay 层 [v0.2+]

| 模块 | 职责 |
|------|------|
| `main_window.py` | 透明无边框置顶窗口、鼠标穿透、全屏覆盖 |
| `danmaku_queue.py` | 弹幕按时间排序、容量控制、按时发射 |
| `danmaku_renderer.py` | QPainter 绘制、60fps 动画、多轨道管理 |
| `tray_icon.py` | 系统托盘、右键退出菜单 |

### 5.4 v0.3+ 阶段新增模块

| 模块 | 职责 |
|------|------|
| `command_handler.py` | 处理用户指令（开关、样式、透明度、速度） |
| `config.py` | JSON 配置文件读写、默认值管理 |

---

## 6. 数据格式规范

### 6.1 Content Script → Background Script

```typescript
// content.js → background.js (chrome.runtime.sendMessage)
interface VideoInfoMessage {
  type: "video_info";
  bv: string;           // BV号
  cid: number | null;   // cid (UrlRegex等Resolver可能拿不到)
  title: string;        // 视频标题
  progress: number;     // 当前播放进度 (秒)
  duration: number | null;  // 视频总时长 (UrlRegex可能拿不到)
  isPlaying: boolean;   // 是否正在播放
  pageUrl: string;      // 当前页面完整URL
  resolverName: string; // 哪个 Resolver 提取到信息的 (用于调试)
}
```

### 6.2 Extension ↔ Python (Native Messaging)

```typescript
// 统一消息信封
interface NativeMessage {
  protocolVersion: number;  // 当前为 1
  id: string;               // UUID v4, 用于追踪
  timestamp: number;        // Unix ms
  type: string;
  payload: object;
}

// ─── Extension → Python ───

// 视频切换 (首次检测到或切换视频时发送)
interface VideoSwitchMessage {
  type: "video_switch";
  payload: {
    bv: string;
    cid: number | null;     // 可能为 null (UrlResolver拿不到)
    title: string;
    duration: number | null;
    pageUrl: string;
  };
}

// 进度更新 (限流: 1次/s)
interface ProgressUpdateMessage {
  type: "progress_update";
  payload: {
    bv: string;
    progress: number;
    isPlaying: boolean;
  };
}

// 心跳 (每30s)
interface HeartbeatMessage {
  type: "heartbeat";
  payload: {};
}

// ─── Python → Extension (MVP 仅回复 status) ───

interface StatusResponse {
  type: "status";
  payload: {
    status: "ok" | "error";
    message?: string;
  };
}
```

> **MVP 注意：** v0.1 阶段 Extension→Python 只使用 `video_switch` 和 `progress_update` 两种消息。Python→Extension 只回复 `{"status":"ok"}`。后续版本在此基础上扩展更多消息类型。

### 6.3 Python 内部事件 (data_dispatcher) [v0.2+]

```python
class EventType(Enum):
    CID_CONFIRMED = "cid_confirmed"
    DANMAKU_LOADED = "danmaku_loaded"
    VIDEO_SWITCHED = "video_switched"
    PROGRESS_UPDATED = "progress_updated"
    STYLE_CHANGED = "style_changed"
    TOGGLE_DANMAKU = "toggle_danmaku"

@dataclass
class CidConfirmedEvent:
    bv: str; cid: int; title: str; duration: float

@dataclass
class DanmakuLoadedEvent:
    bv: str; cid: int; danmaku_list: List; total_count: int

@dataclass
class ProgressUpdatedEvent:
    bv: str; progress: float; is_playing: bool
```

### 6.4 配置数据结构 [v0.3+]

```python
@dataclass
class AppConfig:
    # 窗口
    window_opacity: float = 0.85
    scroll_area_height: int = 35         # 占屏幕高度百分比
    # 弹幕样式
    font_family: str = "Microsoft YaHei"
    font_size: int = 25
    font_outline: bool = True
    # 动画
    scroll_speed: float = 2.0            # 像素/帧
    top_duration: int = 5                # 顶部弹幕停留秒数
    bottom_duration: int = 5
    # 过滤
    enable_scroll: bool = True
    enable_top: bool = True
    enable_bottom: bool = True
    # 网络
    request_timeout: int = 10
    max_retries: int = 3
```

---

## 7. 关键技术方案

### 7.1 Resolver Chain 视频信息提取

content.js 不直接依赖 `window.__INITIAL_STATE__`，而是通过 Resolver Chain 依次尝试多种提取策略。

```
content.js 启动
     │
     ▼
┌─────────────────────────┐
│ URL 匹配 B站视频页？     │
│ /video/* 或 /bangumi/*  │
└────────────┬────────────┘
             │
    ┌────────┴────────┐
    │ 否               │ 是
    ▼                  ▼
  等待导航    ┌─────────────────────────┐
             │ 启动 Resolver Chain      │
             └────────────┬────────────┘
                          │
             ┌────────────▼────────────┐
             │ 1. InitialStateResolver │──成功──▶ 获得 BV/cid/title/duration
             └────────────┬────────────┘
                          │ 失败
             ┌────────────▼────────────┐
             │ 2. UrlRegexResolver     │──成功──▶ 获得 BV (cid=null)
             └────────────┬────────────┘
                          │ 失败
             ┌────────────▼────────────┐
             │ 3. MetaTagResolver      │──成功──▶ 获得 BV (cid=null)
             └────────────┬────────────┘
                          │ 失败
             ┌────────────▼────────────┐
             │ 4. VideoElementResolver │──成功──▶ 获得 BV (cid=null)
             └────────────┬────────────┘
                          │ 全部失败
                          ▼
                    记录错误 + 等待重试

Resolver 成功后:
  → 发送 VIDEO_SWITCH 到 background.js
  → 绑定 video 事件 (play/pause/seeked) + 1s 定时轮询
  → 循环发送 PROGRESS_UPDATE
```

**SPA 页面切换检测：**
- `MutationObserver` 监听 `<title>` 变化
- 定时检查 `location.href`（兜底）
- 检测到变化 → 重新运行 Resolver Chain

### 7.2 弹幕分段获取策略 [v0.2+]

B站弹幕按视频时间分片存储（每段约6分钟）。

```
视频时长: 24分钟 → 约4个分段
  ├── Segment 1: dm.so?oid={cid}&segment_index=1  [0:00 - 6:00)
  ├── Segment 2: dm.so?oid={cid}&segment_index=2  [6:00 - 12:00)
  ├── Segment 3: dm.so?oid={cid}&segment_index=3  [12:00 - 18:00)
  └── Segment 4: dm.so?oid={cid}&segment_index=4  [18:00 - 24:00]

获取策略:
  1. 请求 segment_index=1 → 判断总分段数
  2. 剩余分段并发请求 (Semaphore(5))
  3. 合并 + 排序 + 去重
```

### 7.3 PyQt 透明窗口实现 [v0.2+]

```python
class TransparentOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Windows 鼠标穿透
        hwnd = int(self.winId())
        ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        ctypes.windll.user32.SetWindowLongW(
            hwnd, -20,
            ex_style | 0x80000   # WS_EX_LAYERED
                     | 0x20      # WS_EX_TRANSPARENT
                     | 0x80      # WS_EX_TOOLWINDOW
        )
```

### 7.4 弹幕渲染管线 [v0.2+]

```
每帧 (16ms @ 60fps):

1. QPainter 清空画布 (透明背景)
2. danmaku_queue 拉取当前时间应发射的弹幕
3. 为每条新弹幕分配空闲轨道
4. 遍历所有活跃弹幕:
   - 滚动弹幕: x -= speed; x + width < 0 → 移除
   - 顶部/底部弹幕: 停留计时到期 → 移除
5. 绘制 (QPainter.drawText)
6. 清理过期弹幕
7. end()
```

### 7.5 Native Messaging 连接管理

#### 7.5.1 Manifest V3 Service Worker 生命周期限制

Chrome Extension Manifest V3 的 Service Worker 在以下情况会被浏览器**挂起（suspend）或终止**：

- 空闲约 30 秒后挂起
- 浏览器内存压力时强制终止
- 浏览器重启后需重新加载

这意味着 **Native Messaging 长连接不一定能长期保持**。Service Worker 被挂起时，与 Python 进程的 stdin/stdout 管道可能断开；SW 被终止时，之前建立的连接状态全部丢失。

**设计决策：**

| 连接特性 | MVP 阶段 | v0.3+ |
|----------|----------|-------|
| `connectNative()` 基础连接 | ✓ 必须实现 | ✓ |
| 收到消息后转发给 Python | ✓ 必须实现 | ✓ |
| 断线重连（指数退避） | 保留设计，标记为 Beta | 根据 MVP 实测决定 |
| 30s 心跳保活 | 保留设计，标记为 Beta | 同上 |
| SW 被挂起后恢复连接 | 不实现 | 同上 |

**MVP 原则：** 先验证"用户打开 B站 → 触达 Python"这条链路能否在正常使用场景下稳定工作。复杂重连/心跳机制是锦上添花，不应阻塞 MVP 验收。

#### 7.5.2 连接生命周期（设计目标）

```
Extension 启动 / SW 唤醒 → connectNative()
                               │
                          已连接 ──── 转发消息
                               │ 断开 (SW挂起 / Python退出 / 浏览器关闭)
                          重连中 (退避: 1s→2s→4s→8s, max 30s)
                               │
                          重连成功 → 继续转发
```

> ⚠ 上图是**设计目标**，MVP 只实现基础连接和转发。重连逻辑根据实际测试迭代。

---

## 8. 可维护性与扩展预留设计

### 8.1 变化风险矩阵

| 变化类型 | 概率 | 影响模块 | 应对策略 |
|----------|------|----------|----------|
| B站 `__INITIAL_STATE__` 结构变化 | 高 | content.js | Resolver Chain — 只是链中一环 |
| B站新增视频信息注入方式 | 中 | content.js | 新增 Resolver，追加到链尾 |
| B站弹幕 API URL/参数变化 | 中 | danmaku_fetcher.py | 独立封装 + 端点常量化 |
| B站引入 Protobuf 替代 XML | 中 | danmaku_parser.py | 解析器策略模式，双格式 |
| B站页面 SPA 路由变化 | 中 | content.js | 配置化 URL 模式列表 |
| 登录态需求变化（游客→登录） | 中 | danmaku_fetcher.py | Cookie Provider 抽象 |
| Chrome Extension API 变化 | 低 | background.js | Manifest V3 标准 |
| 操作系统变化（Win→Mac/Linux） | 低 | overlay/ | 平台抽象层 |

### 8.2 Resolver Chain 的扩展机制

这是本项目最重要的可维护性设计。每个 Resolver 独立、无副作用、可任意增删。

**新增 Resolver 只需两步：**
1. 实现 `{ name, resolve() }` 接口
2. 在 Chain 构造函数中追加到 `this.resolvers` 数组

**未来可能的 Resolver：**
- `WindowBiliDataResolver` — 若 B站新增 `window.__BILI_DATA__`
- `PlayerApiResolver` — 若 B站暴露播放器 JS API
- `IframeApiResolver` — 若视频在 iframe 中加载
- `LiveRoomResolver` — 扩展到直播间的信息提取

### 8.3 弹幕格式变化的应对：解析器策略模式 [v0.2+]

```python
class DanmakuParser(ABC):
    @abstractmethod
    def parse(self, raw_data: bytes) -> List[DanmakuItem]: ...

class XmlDanmakuParser(DanmakuParser):      # 当前 XML 格式
    ...

class ProtobufDanmakuParser(DanmakuParser): # 预留 Protobuf 格式
    ...

def get_parser(content_type: str) -> DanmakuParser:
    if 'xml' in content_type:
        return XmlDanmakuParser()
    elif 'protobuf' in content_type:
        return ProtobufDanmakuParser()
    raise ValueError(f"不支持: {content_type}")
```

### 8.4 登录状态变化的应对：Cookie Provider 抽象 [v0.2+]

```python
class CookieProvider(ABC):
    @abstractmethod
    def get_cookie(self) -> Optional[str]: ...

class NoOpCookieProvider(CookieProvider):      # MVP: 游客模式
    def get_cookie(self): return None

class FileCookieProvider(CookieProvider):      # v0.3+: 文件读取
    ...

class ExtensionCookieProvider(CookieProvider): # v0.3+: 扩展获取
    ...
```

### 8.5 协议版本演进

Native Messaging 消息包含 `protocolVersion`，Python 按版本分发：

```python
PROTOCOL_HANDLERS = {
    1: V1Handler(),   # 当前
    # 2: V2Handler(), # 未来
}
```

### 8.6 配置化常量

```python
# danmaku_fetcher.py
BILIBILI_API = {
    'video_info': 'https://api.bilibili.com/x/web-interface/view',
    'danmaku_xml': 'https://api.bilibili.com/x/v1/dm/list.so',
    'danmaku_protobuf': 'https://api.bilibili.com/x/v2/dm/list/seg.so',
}
```

```javascript
// content.js
const BILIBILI_PAGE_PATTERNS = [
    /^https?:\/\/www\.bilibili\.com\/video\//,
    /^https?:\/\/www\.bilibili\.com\/bangumi\//,
    // 未来: /list\//, /live\.bilibili\.com\//
];
```

### 8.7 异常处理与日志设计

桌面工具需要长期稳定运行，统一的日志和异常处理策略从 MVP 阶段就应建立。

#### 8.7.1 日志规范

**Extension 端（JavaScript）：**

```javascript
// content.js + background.js — 使用 console 分级
const LOG_PREFIX = '[BiliDanmaku]';

// 分级使用约定
console.log(LOG_PREFIX, 'Resolver: InitialState ✓');        // info: 正常流程
console.warn(LOG_PREFIX, 'Resolver UrlRegex 降级');          // warn: 降级/可恢复
console.error(LOG_PREFIX, '所有 Resolver 均失败');           // error: 需要关注的错误

// 关键节点日志（MVP 阶段即应记录）
// - Service Worker 启动
// - Native Messaging 连接成功/断开
// - 每条消息的 type 和关键字段
// - Resolver Chain 的降级路径
```

**Python 端：**

```python
# native_host.py — MVP 阶段可用 print(stderr)，v0.2+ 切换到 logging
import logging

# v0.2+ 日志配置：同时输出到文件和 stderr
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('bili_danmaku.log', encoding='utf-8'),
        logging.StreamHandler(sys.stderr),
    ]
)
logger = logging.getLogger('BiliDanmaku')

# 使用示例
logger.info("Native Host 已启动")
logger.info("收到消息 type=%s, bv=%s", msg_type, payload.get('bv'))
logger.warning("cid 为空, 需 Python 补全")  # PARTIAL 级 Resolver
logger.error("消息解析失败: %s", e, exc_info=True)
```

> **阶段过渡：** MVP 用 `print(..., file=sys.stderr)` 快速验证。从 v0.2 起必须切换到 `logging` 模块——届时多模块并行，print 难以区分来源。

#### 8.7.2 关键异常分类与处理原则

**核心原则：单点故障不应导致整个程序崩溃。**

| 异常场景 | 阶段 | 处理方式 | 级别 |
|----------|------|----------|------|
| Resolver Chain 全部失败 | MVP | 记录错误 + 1s后重试 Chain | ERROR |
| Native Messaging 连接断开 | MVP | 记录断开 + 优雅退出循环 | WARNING |
| 收到非法 JSON 消息 | MVP | 跳过该消息 + 记录原始数据截断 | ERROR |
| B站 API 请求超时/失败 | v0.2+ | 重试3次 + 最终记录失败 | ERROR |
| B站 API 返回非预期格式 | v0.2+ | 记录响应截断 + 跳过本次 | ERROR |
| 弹幕 XML 解析失败（单个 segment） | v0.2+ | 跳过该 segment + 继续其他 | WARNING |
| 弹幕 XML 解析失败（全部 segment） | v0.2+ | 通知用户 + 等待下次切换 | ERROR |
| PyQt 单帧渲染异常 | v0.2+ | try/except → 跳过本帧 | WARNING |
| PyQt 窗口创建失败 | v0.2+ | 记录 + 程序退出（PyQt 是必须组件） | CRITICAL |
| 配置文件读取失败 | v0.3+ | 使用默认配置 + 记录警告 | WARNING |

#### 8.7.3 MVP 阶段的 try/except 策略

`native_host.py` 的 `main()` 使用**内层 try/except**（包裹单条消息处理，不包裹整个循环）：

```python
def main():
    logger.info("Native Host 已启动")
    while True:
        msg = read_message()
        if msg is None:
            logger.info("连接断开, 退出")
            break
        try:
            handle_message(msg)   # 单条消息处理
        except Exception as e:
            logger.error("消息处理异常: %s", e, exc_info=True)
            send_message({"status": "error", "message": str(e)})
```

> 这样即使某条消息格式异常导致崩溃，进程仍保持运行，等待下一条消息。

#### 8.7.4 日志文件轮转 [v0.3+]

```python
from logging.handlers import RotatingFileHandler
handler = RotatingFileHandler('bili_danmaku.log', maxBytes=5*1024*1024, backupCount=3)
```

---

## 9. 开发阶段与验收标准

### Phase 1 (MVP v0.1): 自动检测 + 消息到达

**目标：Edge 打开 B站视频 → Python 控制台打印结构化视频信息。**

这是项目的最核心价值验证。不做弹幕获取，不做 PyQt。

**文件（仅4个）：**

| 文件 | 操作 | 说明 |
|------|------|------|
| `extension/manifest.json` | 修改 | 添加 host_permissions、content_scripts |
| `extension/content.js` | 新建 | Resolver Chain 提取 + 播放状态监听 |
| `extension/background.js` | 重写 | connectNative 连接 + 消息转发 + Console 日志 |
| `python/native_host.py` | 修改 | Native Messaging 协议 + 打印消息 + try/except |

**任务清单：**

| # | 任务 | 详情 |
|---|------|------|
| 1.1 | manifest.json | 添加 `host_permissions: ["*://www.bilibili.com/*"]`，注册 content_scripts（matches: `*://www.bilibili.com/video/*`, `*://www.bilibili.com/bangumi/*`），保留 nativeMessaging 权限 |
| 1.2 | content.js — Resolver Chain | 实现 4 个 Resolver（InitialState / UrlRegex / MetaTag / VideoElement），链式调用 |
| 1.3 | content.js — 播放监听 | video 事件 (play/pause/seeked) + 1s 定时轮询，向 background 发消息 |
| 1.4 | content.js — SPA 检测 | MutationObserver 监听 title 变化 + 定时检查 URL |
| 1.5 | background.js | connectNative 连接 + 消息转发 + video_switch / progress_update 区分 + 限流(1次/s) + Console 日志。**[Beta]** 心跳(30s)和断线重连保留代码框架但不作为 MVP 验收项（见 §7.5.1） |
| 1.6 | native_host.py | 实现 read_message / send_message / main 循环，打印结构化消息到 stderr |

**测试策略：**

| 测试类型 | 测试内容 | 方法 | 通过标准 |
|----------|----------|------|----------|
| 手动 | Resolver Chain 各策略 | F12 Console 注入测试代码 | 4个 Resolver 在真实 B站页面均能提取成功 |
| 手动 | Resolver 降级 | 修改页面破坏 InitialState，观察降级 | 自动切换到 UrlRegex Resolver |
| 手动 | content → background 消息 | F12 Service Worker Console | 日志显示消息已转发 |
| 集成 | background → native_host | 注册 Native Host → 打开 B站视频 | Python stderr 打印完整视频信息 |
| 测试 | **[Beta]** 断线重连 | 手动关闭 Python → 重新打开 B站 | Extension 尝试重连（观察项，不阻塞 MVP） |
| 集成 | SPA 切换 | B站内从一个视频切换到另一个 | Python 打印新 BV 号 |
| 手动 | 多页面 | 打开非B站页面 → 切换到B站页面 | 非B站无输出，切到B站后立即有输出 |
| 手动 | 浏览器兼容 | 分别在 Chrome 和 Edge 测试 | 功能一致 |

**验收标准：**
- [ ] Edge 打开 `https://www.bilibili.com/video/BV1xx411c7mD` → 3秒内 Python stderr 打印出 `BV: BV1xx411c7mD`, `标题: xxx`, `播放中: true/false`
- [ ] 视频播放/暂停 → stderr 日志反映 isPlaying 变化
- [ ] 拖动进度条 → stderr 日志反映 progress 变化
- [ ] 切换到另一个视频 → stderr 打印新视频的 BV 号
- [ ] 关闭 B站标签页 → Python 停止收到更新
- [ ] 关闭浏览器 → Python 打印"连接断开, 退出"
- [ ] Chrome 和 Edge 表现一致
- [ ] **[Beta]** 手动 kill Python → 重新打开 B站 → Extension 重连成功（此项为观察项，不阻塞 MVP）

---

### Phase 2 (v0.2): 弹幕获取 + PyQt 渲染

**目标：打开 B站视频 → 桌面自动出现对应的滚动弹幕。**

**新增文件：**

| 文件 | 说明 |
|------|------|
| `python/danmaku_fetcher.py` | B站弹幕 API 调用 |
| `python/danmaku_parser.py` | XML 解析 → DanmakuItem |
| `python/video_info_handler.py` | BV→cid 确认 |
| `python/danmaku_handler.py` | 弹幕获取编排 |
| `python/data_dispatcher.py` | 事件总线 |
| `python/overlay/main_window.py` | PyQt 透明窗口 |
| `python/overlay/danmaku_queue.py` | 弹幕缓冲队列 |
| `python/overlay/danmaku_renderer.py` | 弹幕渲染引擎 |
| `python/overlay/tray_icon.py` | 托盘图标（基础版，仅退出） |
| `tests/mock/sample_danmaku.xml` | 测试用弹幕 XML |
| `tests/test_danmaku_parser.py` | 解析器单测 |
| `tests/test_danmaku_fetcher.py` | 请求构造单测 |

**修改文件：**
- `python/native_host.py` — 接入 data_dispatcher，消息路由到 handler
- `requirements.txt` — 添加 PyQt6, requests, pytest

**任务清单：**

| # | 任务 | 详情 |
|---|------|------|
| 2.1 | danmaku_fetcher | 单分段 HTTP 请求（`dm.so?oid={cid}`）→ 返回 bytes。fetcher/parser 严格分离 |
| 2.2 | danmaku_parser | XML 解析 → `List[DanmakuItem]`，单元测试（sample XML） |
| 2.3 | video_info_handler | BV→cid API 调用。优先使用 FULL Resolver 提供的 cid，PARTIAL 时补全 |
| 2.4 | danmaku_handler | 编排：cid → fetcher → parser → 注入 queue。视频切换时清空旧弹幕 |
| 2.5 | data_dispatcher | 线程安全发布-订阅事件总线 |
| 2.6 | main_window | PyQt 透明置顶窗口、鼠标穿透 |
| 2.7 | danmaku_queue | 弹幕按时间排序、基于真实时间发射 |
| 2.8 | danmaku_renderer | QPainter 滚动弹幕（v0.2 仅 mode=1） |
| 2.9 | tray_icon | 托盘图标 + 退出按钮 |
| 2.10 | 串联 native_host | 接收 video_switch → dispatcher → handler → fetcher → parser → queue → renderer |
| 2.11 | **[Beta]** 并发/重试 | 多分段并发请求 + 重试策略。此特性为优化项，不阻塞 v0.2 验收 |

**测试策略：**

| 测试类型 | 测试内容 | 方法 | 通过标准 |
|----------|----------|------|----------|
| 单元 | `danmaku_parser` 解析 sample XML | pytest | 字段值、数量与 XML 一致 |
| 单元 | `danmaku_fetcher` URL 构造 | pytest + mock | 参数正确 |
| 单元 | `danmaku_queue` 发射逻辑 | pytest | 给定列表和 elapsed，返回正确子集 |
| 集成 | `fetcher` 真实调用 B站 API | pytest 手动运行 | HTTP 200, XML 非空 |
| 集成 | `native_host` → fetcher → parser 链路 | 真实 BV 号 | 完整链路返回弹幕列表 |
| 集成 | parser → queue → renderer | 真实弹幕数据 | 弹幕出现在屏幕上 |
| 手动 | 端到端：打开 B站 → 弹幕出现 | 真实 B站视频 | 3秒内桌面出现弹幕 |
| 手动 | 鼠标穿透 | 点击弹幕区域下方 | 点击穿透 |
| 手动 | 托盘退出 | 右键退出 | 进程退出 |
| 手动 | 视频切换 | 切换 B站视频 | 弹幕更新为新视频 |
| 手动 | 运行稳定性 | 运行 30 分钟 | 无崩溃 |

**验收标准（核心链路）：**
- [ ] `pytest` 单元测试全部通过
- [ ] 打开 B站视频 → 3 秒内桌面出现滚动弹幕（单分段获取即可）
- [ ] 弹幕内容与 B站播放器弹幕一致（抽样对比）
- [ ] 弹幕从右到左平滑滚动，轨道不重叠
- [ ] 鼠标穿透正常
- [ ] 切换视频 → 弹幕更新
- [ ] 关闭视频页 → 弹幕清空
- [ ] 托盘退出正常
- [ ] 运行 30 分钟无崩溃
- [ ] **[Beta]** 多分段并发获取弹幕（长视频场景，不阻塞 v0.2）

---

### Phase 3 (v0.3): 播放同步 + 样式 + 托盘

**目标：** 弹幕与视频精确同步，样式可配置，体验完整。

**新增文件：** `python/config.py`, `python/command_handler.py`, `resources/icon.png`
**修改文件：** `danmaku_renderer.py`（三种模式+样式）, `danmaku_queue.py`（同步模式）, `tray_icon.py`（完整菜单）, `native_host.py`（command 路由）

**任务清单：**

| # | 任务 | 详情 |
|---|------|------|
| 3.1 | 播放同步 | queue 切换到 progress 同步模式 |
| 3.2 | 三种弹幕模式 | mode=4(底部), mode=5(顶部) + 停留计时 |
| 3.3 | 弹幕样式 | 描边、阴影、字体大小可配 |
| 3.4 | config.py | JSON 配置读写 |
| 3.5 | tray_icon | 完整菜单：开关、样式、退出 |
| 3.6 | command_handler | 指令 → dispatcher |

**验收标准：**
- [ ] 弹幕与视频时间误差 < 1s
- [ ] 暂停视频 → 弹幕停止
- [ ] 三种模式同时正确显示
- [ ] 配置文件生效
- [ ] 托盘菜单操作正常

---

### Phase 4 (v1.0): 安装打包

**新增文件：** `install.bat`, `README.md`

**任务清单：**

| # | 任务 | 详情 |
|---|------|------|
| 4.1 | install.bat | 检测 Python、安装依赖、注册 Native Host (Chrome+Edge) |
| 4.2 | 性能优化 | 弹幕 > 100条/帧时 ≥ 30fps |
| 4.3 | README | 安装步骤、使用说明、排错 |
| 4.4 | PyInstaller | 可选：打包为独立 exe |

**验收标准：**
- [ ] `install.bat` 一键安装成功
- [ ] 弹幕量 ≥ 100条/秒时帧率 ≥ 30fps
- [ ] Chrome 和 Edge 均通过
- [ ] 运行 2 小时无内存泄漏

---

## 10. 附录

### 10.1 B站页面关键数据路径

```
播放页URL模式:
  - https://www.bilibili.com/video/{BV号}
  - https://www.bilibili.com/video/{BV号}/?p={分P号}
  - https://www.bilibili.com/bangumi/play/ep{epid}
  - https://www.bilibili.com/bangumi/play/ss{seasonid}

关键数据源 (按优先级):
  1. window.__INITIAL_STATE__.videoData.{bvid, cid, title, duration}
  2. URL 正则: /video/(BV[a-zA-Z0-9]+)
  3. <meta itemprop="url"> content 属性
  4. <video> 元素: .currentTime, .duration, .paused, src 属性

注意: __INITIAL_STATE__ 是主要来源但不是唯一来源。
     Resolver Chain 设计确保任一来源可用即可工作。
```

### 10.2 B站 API 接口清单

| 接口 | 方法 | URL | 说明 |
|------|------|-----|------|
| 视频信息 | GET | `https://api.bilibili.com/x/web-interface/view?bvid={bv}` | 获取 cid、分P、时长 |
| 弹幕XML | GET | `https://api.bilibili.com/x/v1/dm/list.so?oid={cid}&segment_index={n}` | 弹幕分段 |
| 弹幕Protobuf | GET | `https://api.bilibili.com/x/v2/dm/list/seg.so?oid={cid}&segment_index={n}` | 新协议（预留） |

### 10.3 Python 依赖

```txt
# requirements.txt (v0.2+)
PyQt6>=6.5
requests>=2.28
pytest>=7.0

# v0.3+ 额外:
# pydantic>=2.0

# v1.0 额外:
# pyinstaller>=5.0
```

> MVP 阶段 `requirements.txt` 为空（Python 标准库即可满足）。

### 10.4 Native Messaging Host 注册 (Windows)

`native_host.json` 模板：
```json
{
    "name": "com.bili.danmaku",
    "description": "BiliDanmaku Native Messaging Host",
    "path": "{PYTHON_EXE_PATH}",
    "type": "stdio",
    "allowed_origins": [
        "chrome-extension://{EXTENSION_ID}/"
    ]
}
```

注册表路径：
- Chrome: `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.bili.danmaku`
- Edge: `HKCU\Software\Microsoft\Edge\NativeMessagingHosts\com.bili.danmaku`

### 10.5 性能预算

| 指标 | MVP | v1.0 |
|------|-----|------|
| 消息延迟 (扩展→Python) | < 100ms | < 50ms |
| 弹幕获取延迟 | N/A | < 3s (首次) |
| 渲染帧率 | N/A | ≥ 30fps (100条/秒) |
| CPU (空闲) | < 1% | < 5% |
| 内存 | < 50MB | < 150MB |

### 10.6 版本与文件对照表

| 文件 | MVP | v0.2 | v0.3 | v1.0 |
|------|:---:|:----:|:----:|:----:|
| `extension/manifest.json` | ● | ● | ● | ● |
| `extension/content.js` | ● | ● | ● | ● |
| `extension/background.js` | ● | ● | ● | ● |
| `python/native_host.py` | ● | ● | ● | ● |
| `python/danmaku_fetcher.py` | — | ● | ● | ● |
| `python/danmaku_parser.py` | — | ● | ● | ● |
| `python/video_info_handler.py` | — | ● | ● | ● |
| `python/danmaku_handler.py` | — | ● | ● | ● |
| `python/data_dispatcher.py` | — | ● | ● | ● |
| `python/command_handler.py` | — | — | ● | ● |
| `python/config.py` | — | — | ● | ● |
| `python/overlay/main_window.py` | — | ● | ● | ● |
| `python/overlay/danmaku_queue.py` | — | ● | ● | ● |
| `python/overlay/danmaku_renderer.py` | — | ● | ● | ● |
| `python/overlay/tray_icon.py` | — | ● | ● | ● |
| `native_host.json` | ● | ● | ● | ● |
| `install.bat` | — | — | — | ● |

> ● = 存在 &nbsp;&nbsp; — = 不存在

### 10.7 Native Messaging 开发调试指南

MVP 阶段最关键的调试链路是：**Extension → Native Messaging → Python**。以下是开发阶段的具体操作步骤。

#### 10.7.1 注册 Native Messaging Host

**Step 1：确定 Extension ID**

加载未打包扩展后，在 `chrome://extensions` 页面查看扩展 ID（如 `abcdefghijklmnopqrstuvwxyz123456`）。

**Step 2：编写 `native_host.json`**

```json
{
    "name": "com.bili.danmaku",
    "description": "BiliDanmaku Native Messaging Host",
    "path": "C:\\path\\to\\python\\native_host.py",
    "type": "stdio",
    "allowed_origins": [
        "chrome-extension://{EXTENSION_ID}/"
    ]
}
```

> ⚠ `path` 需要指向 **Python 可执行文件的绝对路径**（如 `C:\\Users\\xxx\\AppData\\Local\\Programs\\Python\\Python310\\python.exe`），不是指向 `.py` 文件。`.py` 文件路径应通过启动参数传递。

**Step 3：注册到 Windows 注册表**

```cmd
:: Chrome
REG ADD "HKCU\Software\Google\Chrome\NativeMessagingHosts\com.bili.danmaku" /ve /t REG_SZ /d "C:\path\to\native_host.json" /f

:: Edge
REG ADD "HKCU\Software\Microsoft\Edge\NativeMessagingHosts\com.bili.danmaku" /ve /t REG_SZ /d "C:\path\to\native_host.json" /f
```

#### 10.7.2 单独测试 native_host.py

在接入浏览器之前，先用命令行模拟 Native Messaging 协议测试 Python 端：

```bash
# 准备测试消息: 4字节LE长度 + JSON
# 消息内容: {"type":"video_switch","payload":{"bv":"BV1xx411c7mD","cid":null,"title":"测试视频","duration":null,"pageUrl":"https://www.bilibili.com/video/BV1xx411c7mD"}}
echo -n '{"type":"video_switch","payload":{"bv":"BV1xx411c7mD","cid":null,"title":"测试","duration":null,"pageUrl":"..."}}' | python native_host.py
```

或编写一个简单的 Python 测试脚本 `test_native_host.py` 来做协议编码：

```python
import struct, json, subprocess

msg = json.dumps({"type":"video_switch","payload":{"bv":"BV1xx411c7mD","cid":None,"title":"测试","duration":None,"pageUrl":"..."}})
data = msg.encode('utf-8')
packet = struct.pack('<I', len(data)) + data

proc = subprocess.Popen(['python', 'native_host.py'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
stdout, stderr = proc.communicate(packet)
print("STDERR:", stderr.decode())
print("STDOUT:", stdout[:100])
```

#### 10.7.3 查看 Chrome/Edge Extension 日志

| 日志来源 | 查看方式 |
|----------|----------|
| **content.js** 的 `console.log` | F12 → Console（在 B站页面标签下） |
| **background.js (Service Worker)** 的 `console.log` | `chrome://extensions` → 点击扩展详情 → "Service Worker" → 点击 "Inspect views" 链接 |
| **Native Messaging 错误** | 同上 Service Worker 控制台，连接失败错误会显示在此处 |
| **Python stderr** | 取决于启动方式。手动启动时直接在终端可见；由 Chrome 启动时可能不可见（建议 MVP 阶段手动启动 Python 来调试） |

#### 10.7.4 常见问题排查

| 现象 | 可能原因 | 排查方法 |
|------|----------|----------|
| 扩展加载后没有任何反应 | content.js 未匹配到 URL | F12 Console 看是否有 `[BiliDanmaku]` 日志 |
| content.js 有日志但 background 无反应 | `chrome.runtime.sendMessage` 失败 | Service Worker Console 看是否有错误 |
| background 有日志但 Python 无反应 | Native Host 注册不正确 | 检查注册表路径、JSON 文件路径、`allowed_origins` 中的扩展 ID |
| Python 启动后立即退出 | stdin 读取失败或协议解析错误 | 在 `native_host.py` 开头加 `open('debug.log','w')` 写入调试信息 |
| `Specified native messaging host not found` | 注册表路径错误或 JSON 文件不存在 | 检查 `REG QUERY "HKCU\Software\Google\Chrome\NativeMessagingHosts\com.bili.danmaku"` |
| `Native host has exited` | Python 脚本崩溃或路径中的 Python 不存在 | 直接在终端运行 Python 脚本看报错 |

#### 10.7.5 MVP 推荐调试流程

```
1. 先用 Python 测试脚本验证 native_host.py 协议正确
   → python test_native_host.py
   → 确认 stderr 输出包含正确的 BV/标题

2. 加载扩展，打开 B站视频页
   → F12 Console 确认 content.js Resolver 工作
   → chrome://extensions → Service Worker Inspect 确认 background.js 工作

3. 手动启动 Python（终端运行）
   → python native_host.py
   → 观察 stderr 是否打印消息

4. 若第3步不通 → 检查 Native Host 注册表 + JSON 配置
   → 检查 Service Worker Console 是否有连接错误
```

---

### 10.8 Phase 1 (MVP) Python 模块说明

MVP 阶段 Python 端**只有一个文件 `native_host.py`**，约 50 行代码。原因：

1. **需求驱动拆分**：只有一个职责（收消息+打印），不需要多个模块
2. **避免过度设计**：如果一开始就引入 `data_dispatcher`、`video_info_handler`，在没有任何内部消费者的情况下只是空壳
3. **自然演进**：Phase 2 需要弹幕获取和 PyQt 渲染时，`native_host.py` 的消息处理逻辑自然会膨胀——那时拆出 `data_dispatcher` 和各 handler 是水到渠成的

当前 `native_host.py` 的代码见 [§5.2.3](#523-native_hostpy--mvp-唯一-python-模块)。
