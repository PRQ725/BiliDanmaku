# danmaku_parser.py — B站弹幕 XML 解析器
# 将 B站弹幕 API 返回的 XML 解析为结构化 DanmakuItem 列表。
#
# 职责边界:
#   - 输入: 原始 XML bytes (由 danmaku_fetcher 提供)
#   - 输出: DanmakuParseResult (包含 List[DanmakuItem] + 统计信息)
#   - 不负责 HTTP 请求, 不关心数据来源
#
# 依赖: Python 3.8+ 标准库 (xml.etree.ElementTree)

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List


@dataclass
class DanmakuItem:
    """单条弹幕的完整结构化表示。

    所有字段来源于 XML <d> 标签 p 属性的逗号分隔值。
    """
    time: float        # 弹幕出现时间 (秒), p[0]
    content: str       # 弹幕文本内容 (XML 标签内文本)
    mode: int          # 弹幕模式: 1=滚动, 4=底部, 5=顶部, p[1]
    font_size: int     # 字号: 18/25/36, p[2]
    color: int         # RGB 颜色值 (十进制), p[3]
    timestamp: int     # Unix 发送时间戳, p[4]
    danmaku_id: int    # 弹幕数据库 rowID (去重用), p[7]
    pool: int          # 弹幕池: 0=普通池, 1=字幕池, p[5]

    # 预留: p[6] 为 user_id hash, 当前不存储


@dataclass
class DanmakuParseResult:
    """弹幕解析结果容器。

    为后续版本预留扩展字段 (如 total_segments、parse_duration_ms 等统计)。
    """
    items: List[DanmakuItem] = field(default_factory=list)
    total: int = 0                   # 成功解析的弹幕总数
    source: str = 'xml_v1'           # 解析器来源标识
    skipped: int = 0                 # 跳过的异常 <d> 条目数

    # ── 预留扩展字段 (v0.3+) ──
    # total_segments: int = 0        # 多分段时的总段数
    # parse_duration_ms: float = 0.0 # 解析耗时


def parse_xml(raw_data: bytes) -> DanmakuParseResult:
    """解析 B站弹幕 XML，返回结构化结果。

    Args:
        raw_data: B站 dm.so 接口返回的原始 XML 字节流 (UTF-8)。

    Returns:
        DanmakuParseResult: 包含解析后的弹幕列表和统计信息。

    Raises:
        ValueError: XML 格式严重错误（根元素缺失/解析失败）时抛出。
                    单条 <d> 属性异常不会导致整体失败，会跳过并记录 skipped 计数。
    """
    if not raw_data or not raw_data.strip():
        return DanmakuParseResult()

    try:
        root = ET.fromstring(raw_data)
    except ET.ParseError as e:
        raise ValueError(f'弹幕 XML 解析失败: {e}') from e

    items: List[DanmakuItem] = []
    skipped = 0

    for elem in root.iter('d'):
        try:
            item = _parse_d_element(elem)
            items.append(item)
        except (ValueError, IndexError) as e:
            skipped += 1
            print(
                f'[BiliDanmaku] 跳过异常弹幕条目: {e}',
                file=sys.stderr,
            )

    return DanmakuParseResult(
        items=items,
        total=len(items),
        skipped=skipped,
    )


def _parse_d_element(elem: ET.Element) -> DanmakuItem:
    """解析单个 <d> 元素为 DanmakuItem。

    <d> 标签格式:
        <d p="time,mode,font_size,color,timestamp,pool,user_id,danmaku_id">
            弹幕文本
        </d>

    Raises:
        ValueError: p 属性字段数不足或数值类型错误。
        IndexError: p 属性字段缺失。
    """
    p_raw = elem.get('p')
    if not p_raw:
        raise ValueError('<d> 缺少 p 属性')

    parts = p_raw.split(',')
    if len(parts) < 8:
        raise ValueError(
            f'p 属性字段不足 (期望 >=8, 实际 {len(parts)}): '
            f'p="{p_raw[:60]}..."' if len(p_raw) > 60 else f'p="{p_raw}"'
        )

    content = (elem.text or '').strip()

    return DanmakuItem(
        time=float(parts[0]),
        mode=int(parts[1]),
        font_size=int(parts[2]),
        color=int(parts[3]),
        timestamp=int(parts[4]),
        pool=int(parts[5]),
        # parts[6] = user_id hash, 当前不存储
        danmaku_id=int(parts[7]),
        content=content,
    )
