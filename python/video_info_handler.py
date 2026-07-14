# video_info_handler.py — 视频信息处理 (BV → cid 补全)
# 当 Resolver Chain 返回 PARTIAL 级别结果 (cid=null) 时，
# 通过 B站 API 查询完整视频信息并补全 cid。
#
# 职责边界:
#   - FULL Resolver 已有 cid → 不触发，直接使用
#   - PARTIAL Resolver (cid=null) → 调用 API 补全
#   - 缓存已查询过的 BV→cid 映射，避免重复请求
#
# 测试模式:
#   设置环境变量 BILIDANMAKU_TEST_MODE=1 可跳过真实 HTTP 请求，
#   直接抛出 ValueError 模拟 API 失败。集成测试专用。
#
# 依赖: Python 3.8+ 标准库 (urllib.request, json)

from __future__ import annotations

import json
import os
import urllib.request
from constants import BILIBILI_API, HTTP_HEADERS, TIMEOUTS

# ── 简单 dict 缓存 ─────────────────────────────────────────────
# key: bvid (str), value: {'cid': int, 'title': str, 'duration': float}
# alpha 阶段不做容量限制和淘汰策略 (v0.3+ 按 CID_CACHE_MAX_SIZE 实现)
_cid_cache: dict[str, dict] = {}


def fetch_video_info(bvid: str) -> dict:
    """查询 B站视频信息，获取 cid / title / duration。

    优先从缓存读取；缓存未命中时调用 B站 API。

    Args:
        bvid: B站 BV 号 (如 "BV1xx411c7mD")。

    Returns:
        dict: {'cid': int, 'title': str, 'duration': float}

    Raises:
        urllib.error.URLError: 网络连接失败。
        urllib.error.HTTPError: HTTP 非 2xx 响应 (含 -412 视频不存在等)。
        KeyError / TypeError: API 响应格式变化 (缺少预期字段)。
        ValueError: 测试模式下直接抛出。
    """
    if os.environ.get('BILIDANMAKU_TEST_MODE') == '1':
        raise ValueError('B站视频信息 API 返回错误 (code=-404): 啥都木有')

    if bvid in _cid_cache:
        return _cid_cache[bvid]

    url = f'{BILIBILI_API["video_info"]}?bvid={bvid}'
    req = urllib.request.Request(url, headers=HTTP_HEADERS)

    with urllib.request.urlopen(req, timeout=TIMEOUTS['read']) as resp:
        body = json.loads(resp.read().decode('utf-8'))

    # B站 API 响应结构: {"code": 0, "data": {"cid": ..., "title": ..., "duration": ...}}
    code = body.get('code')
    if code != 0:
        message = body.get('message', '未知错误')
        raise ValueError(f'B站视频信息 API 返回错误 (code={code}): {message}')

    data = body['data']
    result = {
        'cid': data['cid'],
        'title': data.get('title', ''),
        'duration': data.get('duration', 0.0),
    }

    _cid_cache[bvid] = result
    return result


def get_cached_cid(bvid: str) -> dict | None:
    """仅从缓存获取，不触发 API 请求。未命中返回 None。"""
    return _cid_cache.get(bvid)


def clear_cache() -> None:
    """清空所有缓存 (用于测试)。"""
    _cid_cache.clear()
