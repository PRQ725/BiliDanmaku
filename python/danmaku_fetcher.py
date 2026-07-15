# danmaku_fetcher.py — B站弹幕 API HTTP 请求
# 封装 B站弹幕接口的 HTTP GET 请求，返回原始 bytes。
#
# 职责边界:
#   - 只负责 HTTP 传输: 构造请求 → 发送 → 返回原始响应体
#   - 不解析响应内容 (由 danmaku_parser 负责)
#   - 不处理重试/并发 (v0.3+)
#
# 测试模式:
#   设置环境变量 BILIDANMAKU_TEST_MODE=1 可跳过真实 HTTP 请求，
#   返回最小有效 XML 供 parser 验证。集成测试专用。
#
# 依赖: Python 3.8+ 标准库 (urllib.request)

from __future__ import annotations

import gzip
import os
import sys
import urllib.error
import urllib.request
import zlib
from constants import BILIBILI_API, HTTP_HEADERS, TIMEOUTS

# Minimal valid B站 danmaku XML used in test mode
# (built with .encode() to allow non-ASCII characters)
_TEST_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<i>\n'
    '  <chatserver>chat.bilibili.com</chatserver>\n'
    '  <chatid>0</chatid>\n'
    '  <mission>0</mission>\n'
    '  <maxlimit>1000</maxlimit>\n'
    '  <state>0</state>\n'
    '  <real_name>0</real_name>\n'
    '  <source>test</source>\n'
    '  <d p="1.5,1,25,16777215,1700000000,0,uid001,2001">test-danmaku-1</d>\n'
    '  <d p="2.0,1,25,16776960,1700000001,0,uid002,2002">test-danmaku-2</d>\n'
    '  <d p="5.5,5,18,16711680,1700000002,0,uid003,2003">top-danmaku</d>\n'
    '</i>\n'
).encode('utf-8')


def _looks_like_xml(data: bytes) -> bool:
    """快速判断：响应是否像 XML 或 B站弹幕数据。

    检查前 200 字节是否以 XML 声明或弹幕根元素开头。
    JSON/HTML/空内容返回 False。
    """
    if not data or not data.strip():
        return False
    text = data[:200].lstrip()
    # XML 声明 <?xml ...?> 或弹幕根元素 <i> 或 <i ...>
    return text.startswith(b'<?xml') or text.startswith(b'<i') or text.startswith(b'<I')


def _build_headers(cookie: str | None = None) -> dict:
    """构造请求头，合并常量和可选的 Cookie。

    Args:
        cookie: 浏览器 cookie 字符串 (如 "buvid3=xxx; buvid4=yyy")。
                未登录用户也有指纹 cookie，B站弹幕 API 需要。

    Returns:
        dict: 完整的请求头。
    """
    headers = dict(HTTP_HEADERS)
    if cookie:
        headers['Cookie'] = cookie
    return headers


def _log_response_info(resp, raw: bytes, url: str) -> None:
    """输出调试日志：HTTP status / headers / body 预览。"""
    print(f'[BiliDanmaku] danmaku_fetcher 调试:', file=sys.stderr)
    print(f'  URL: {url}', file=sys.stderr)
    print(f'  HTTP status: {resp.status}', file=sys.stderr)
    print(f'  Content-Type: {resp.headers.get("Content-Type", "(未提供)")}', file=sys.stderr)
    print(f'  Content-Encoding: {resp.headers.get("Content-Encoding", "(未提供)")}', file=sys.stderr)
    print(f'  Content-Length: {resp.headers.get("Content-Length", "(未提供)")}', file=sys.stderr)
    print(f'  raw bytes 长度: {len(raw)}', file=sys.stderr)
    # 安全截断前 200 字节
    preview = raw[:200]
    try:
        preview_text = preview.decode('utf-8', errors='replace')
    except Exception:
        preview_text = repr(preview)
    print(f'  raw 前200字节: {preview_text}', file=sys.stderr)


def _decompress_response(raw: bytes, content_encoding: str) -> tuple[bytes, str]:
    """根据 Content-Encoding 解压响应体。

    urllib.request 不会自动解压，需要手动处理。
    支持 deflate (raw / zlib-wrapped) 和 gzip。

    Args:
        raw: 压缩前的原始字节。
        content_encoding: Content-Encoding 响应头值。

    Returns:
        (decompressed_bytes, method_label) — method_label 用于日志。

    Raises:
        ValueError: 不支持的编码或解压失败。
    """
    encoding = content_encoding.strip().lower()
    if not encoding or encoding == 'identity':
        return raw, 'identity (无压缩)'

    if encoding == 'gzip' or encoding == 'x-gzip':
        try:
            decompressed = gzip.decompress(raw)
            return decompressed, 'gzip'
        except Exception as e:
            raise ValueError(f'gzip 解压失败: {e}') from e

    if encoding == 'deflate':
        # deflate 有两种包装方式:
        #   1. raw deflate (RFC 1951) — B站常用
        #   2. zlib-wrapped (RFC 1950) — 有 2 字节头 + 4 字节 Adler-32 尾
        # 先尝试 raw deflate, 失败再尝试 zlib-wrapped
        try:
            decompressed = zlib.decompress(raw, -zlib.MAX_WBITS)
            return decompressed, 'deflate (raw)'
        except zlib.error:
            try:
                decompressed = zlib.decompress(raw)
                return decompressed, 'deflate (zlib)'
            except zlib.error as e:
                raise ValueError(f'deflate 解压失败 (raw 和 zlib 均失败): {e}') from e

    # brotli / zstd / 其他 — v0.2.0-alpha 不支持
    raise ValueError(
        f'不支持的 Content-Encoding: "{content_encoding}"。'
        f'当前仅支持 gzip 和 deflate。'
    )


def fetch_danmaku_raw(cid: int, segment_index: int = 1,
                      cookie: str | None = None) -> bytes:
    """获取弹幕原始 XML 响应。

    Args:
        cid: 视频 cid (从 video_info_handler 或 FULL Resolver 获取)。
        segment_index: 分段索引，每段约 6 分钟。v0.2.0-alpha 仅请求单分段。
        cookie: 浏览器 B站页面的 cookie 字符串。
                未登录用户也需提供 buvid3/buvid4 指纹 cookie。
                v0.2.0-alpha 由扩展通过 Native Messaging 传入。

    Returns:
        B站弹幕 API 返回的原始 XML 字节流 (UTF-8 编码)。

    Raises:
        urllib.error.URLError: 网络连接失败。
        urllib.error.HTTPError: HTTP 非 2xx 响应 (含 412 风控拦截)。
        ValueError: cid 非法 (<=0) 或响应内容非 XML。
    """
    if os.environ.get('BILIDANMAKU_TEST_MODE') == '1':
        return _TEST_XML

    if cid <= 0:
        raise ValueError(f'cid 必须为正整数, 实际: {cid}')

    url = f'{BILIBILI_API["danmaku_xml"]}?oid={cid}&segment_index={segment_index}'
    headers = _build_headers(cookie)
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUTS['read']) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        # 读取错误响应体（可能包含风控页面或 JSON 错误信息）
        error_body = b''
        try:
            error_body = e.read()
        except Exception:
            pass

        _log_http_error(e, error_body, url)
        raise  # 重新抛出，由上层 handler 捕获并生成错误摘要

    # ── 解压前日志 ───────────────────────────────────────
    content_encoding = resp.headers.get('Content-Encoding', 'identity')
    _log_response_info(resp, raw, url)

    # ── Content-Encoding 解压 ────────────────────────────
    if content_encoding and content_encoding.strip().lower() not in ('', 'identity'):
        raw_before = len(raw)
        try:
            raw, method = _decompress_response(raw, content_encoding)
            raw_after = len(raw)
            print(f'[BiliDanmaku]   解压方式: {method}', file=sys.stderr)
            print(f'[BiliDanmaku]   解压前: {raw_before} bytes', file=sys.stderr)
            print(f'[BiliDanmaku]   解压后: {raw_after} bytes ({raw_after - raw_before:+d})', file=sys.stderr)
            # 解压后预览前 200 字节
            try:
                preview = raw[:200].decode('utf-8', errors='replace')
            except Exception:
                preview = repr(raw[:200])
            print(f'[BiliDanmaku]   解压后前200字节: {preview}', file=sys.stderr)
        except ValueError as e:
            print(f'[BiliDanmaku]   解压失败: {e}', file=sys.stderr)
            raise

    # ── 响应验证 (针对解压后的数据) ───────────────────────
    if not raw or not raw.strip():
        raise ValueError(
            f'B站弹幕 API 返回空响应 (cid={cid})。'
            f'HTTP status={resp.status}, '
            f'Content-Type={resp.headers.get("Content-Type", "?")}'
        )

    if not _looks_like_xml(raw):
        preview_text = raw[:200].decode('utf-8', errors='replace')
        raise ValueError(
            f'B站返回非 XML 数据，可能是游客限制或接口变化。\n'
            f'  HTTP status: {resp.status}\n'
            f'  Content-Type: {resp.headers.get("Content-Type", "?")}\n'
            f'  raw 前200字节: {preview_text}'
        )

    return raw


def _log_http_error(error: urllib.error.HTTPError, error_body: bytes,
                    url: str) -> None:
    """输出 HTTP 错误 (如 412) 的详细诊断信息。"""
    print(f'[BiliDanmaku] danmaku_fetcher HTTP 错误:', file=sys.stderr)
    print(f'  URL: {url}', file=sys.stderr)
    print(f'  HTTP status: {error.code}', file=sys.stderr)
    print(f'  Reason: {error.reason}', file=sys.stderr)
    # 打印所有响应头（可能包含风控 token）
    print(f'  Response headers:', file=sys.stderr)
    for key, value in error.headers.items():
        print(f'    {key}: {value}', file=sys.stderr)
    # 打印错误响应体（可能有 JSON 错误信息或风控页面）
    if error_body:
        print(f'  error body 长度: {len(error_body)}', file=sys.stderr)
        try:
            preview = error_body[:500].decode('utf-8', errors='replace')
        except Exception:
            preview = repr(error_body[:200])
        print(f'  error body 前500字节: {preview}', file=sys.stderr)

    # 412 专项诊断提示
    if error.code == 412:
        set_cookie = error.headers.get('Set-Cookie', '')
        print(f'[BiliDanmaku] >>> 412 风控拦截诊断:', file=sys.stderr)
        print(f'[BiliDanmaku]     可能原因: 缺少 Cookie (buvid3/buvid4)', file=sys.stderr)
        print(f'[BiliDanmaku]     可能原因: 请求头不足 (Origin/Referer)', file=sys.stderr)
        if 'X-BILI-SEC-TOKEN' in set_cookie:
            print(f'[BiliDanmaku]     检测到 X-BILI-SEC-TOKEN 挑战', file=sys.stderr)
        if cookie_header := error.headers.get('X-Bili-Cookie-Required'):
            print(f'[BiliDanmaku]     服务器要求 Cookie: {cookie_header}', file=sys.stderr)
