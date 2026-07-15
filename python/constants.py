# constants.py — BiliDanmaku 集中常量管理
# 所有 API 地址、请求头、超时等配置统一在此定义，避免硬编码分散。
#
# 用法:
#   from constants import BILIBILI_API, HTTP_HEADERS, TIMEOUTS
#
# 依赖: Python 3.8+ 标准库（零外部依赖）

# ── B站 API 端点 ──────────────────────────────────────────────

BILIBILI_API = {
    # 弹幕 XML 接口 (v1)
    # GET ?oid={cid}&segment_index={n}
    'danmaku_xml': 'https://api.bilibili.com/x/v1/dm/list.so',

    # 视频信息接口
    # GET ?bvid={bv}
    'video_info': 'https://api.bilibili.com/x/web-interface/view',

    # 弹幕 Protobuf 接口 (v2, 预留)
    # GET ?oid={cid}&segment_index={n}
    'danmaku_protobuf': 'https://api.bilibili.com/x/v2/dm/list/seg.so',
}

# ── HTTP 请求配置 ─────────────────────────────────────────────

HTTP_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/131.0.0.0 Safari/537.36'
    ),
    'Referer': 'https://www.bilibili.com/',
    'Origin': 'https://www.bilibili.com',
    'Accept': 'application/xml, text/xml, */*',
}

TIMEOUTS = {
    'connect': 5,    # 连接超时 (秒)
    'read': 10,      # 读取超时 (秒)
}

# ── Native Messaging 协议常量 ──────────────────────────────────

# 单条消息最大字节数 (1 MB)
MAX_MESSAGE_BYTES = 1024 * 1024

# ── 缓存配置 ───────────────────────────────────────────────────

# video_info_handler cid 缓存最大条目数
CID_CACHE_MAX_SIZE = 20
