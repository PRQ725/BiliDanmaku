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

import os
import urllib.request
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


def fetch_danmaku_raw(cid: int, segment_index: int = 1) -> bytes:
    """获取弹幕原始 XML 响应。

    Args:
        cid: 视频 cid (从 video_info_handler 或 FULL Resolver 获取)。
        segment_index: 分段索引，每段约 6 分钟。v0.2.0-alpha 仅请求单分段。

    Returns:
        B站弹幕 API 返回的原始 XML 字节流 (UTF-8 编码)。

    Raises:
        urllib.error.URLError: 网络连接失败。
        urllib.error.HTTPError: HTTP 非 2xx 响应。
        ValueError: cid 非法 (<=0)。
    """
    if os.environ.get('BILIDANMAKU_TEST_MODE') == '1':
        return _TEST_XML

    if cid <= 0:
        raise ValueError(f'cid 必须为正整数, 实际: {cid}')

    url = f'{BILIBILI_API["danmaku_xml"]}?oid={cid}&segment_index={segment_index}'

    req = urllib.request.Request(url, headers=HTTP_HEADERS)

    # urllib 的 timeout 参数同时覆盖 connect 和 read
    # 使用 read timeout 值 (10s) 作为总超时，确保慢速响应也能完整接收
    with urllib.request.urlopen(req, timeout=TIMEOUTS['read']) as resp:
        return resp.read()
