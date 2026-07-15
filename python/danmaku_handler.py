# danmaku_handler.py — 弹幕获取编排层
# 协调 video_info_handler → danmaku_fetcher → danmaku_parser 全流程，
# 并生成人类可读的摘要文本供 native_host.py 输出。
#
# 职责边界:
#   - 编排弹幕获取的完整流程 (cid 补全 → 请求 → 解析)
#   - 生成摘要字符串 (native_host.py 只负责打印)
#   - 不涉及 data_dispatcher / danmaku_queue (v0.2.x PyQt 阶段引入)
#   - 不处理 progress_update (v0.3+ 播放同步阶段)
#
# 依赖: Python 3.8+ 标准库

from __future__ import annotations

import sys
import traceback
from typing import List

from danmaku_fetcher import fetch_danmaku_raw
from danmaku_parser import DanmakuItem, DanmakuParseResult, parse_xml
from video_info_handler import fetch_video_info


def handle_video_switch(
    bv: str,
    cid: int | None,
    title: str = '',
    resolver_level: str = 'UNKNOWN',
    cookie: str | None = None,
) -> dict:
    """处理视频切换事件，获取弹幕数据。

    编排完整链路:
        1. cid 为 null → video_info_handler 补全
        2. danmaku_fetcher 请求 XML
        3. danmaku_parser 解析为 DanmakuItem 列表
        4. 生成人类可读摘要

    Args:
        bv: BV 号。
        cid: cid (FULL Resolver 提供) 或 None (PARTIAL Resolver 需补全)。
        title: 视频标题。
        resolver_level: Resolver 级别 ("FULL" / "PARTIAL" / "UNKNOWN")。

    Returns:
        dict:
            {
                'success': bool,
                'summary': str,                    # 人类可读摘要，可直接 print
                'result': DanmakuParseResult | None,
                'error': str | None,
                'cid': int | None,                 # 最终 cid（来自 Resolver 或补全）
            }
    """
    lines: List[str] = []
    parse_result: DanmakuParseResult | None = None

    # ── Step 1: cid 补全 ──────────────────────────────────────
    if cid is None:
        lines.append(f'[BiliDanmaku] ─── 弹幕获取 (PARTIAL 补全) ───')
        lines.append(f'[BiliDanmaku]   BV: {bv}')
        lines.append(f'[BiliDanmaku]   标题: {title}')
        lines.append(f'[BiliDanmaku]   Resolver: {resolver_level} → 正在补全 cid...')

        try:
            info = fetch_video_info(bv)
            cid = info['cid']
            if not title:
                title = info.get('title', '')
            lines.append(f'[BiliDanmaku]   cid 补全成功: {cid}')
            if info.get('duration'):
                dur = info['duration']
                lines.append(
                    f'[BiliDanmaku]   时长: {dur}s '
                    f'({int(dur // 60)}分{int(dur % 60)}秒)'
                )
        except Exception as e:
            lines.append(f'[BiliDanmaku]   cid 补全失败: {e}')
            return {
                'success': False,
                'summary': '\n'.join(lines),
                'result': None,
                'error': str(e),
                'cid': None,
            }
    else:
        lines.append(f'[BiliDanmaku] ─── 弹幕获取 (FULL) ───')
        lines.append(f'[BiliDanmaku]   BV: {bv}')
        lines.append(f'[BiliDanmaku]   标题: {title}')
        lines.append(f'[BiliDanmaku]   cid: {cid}')
        lines.append(f'[BiliDanmaku]   Resolver: {resolver_level}')

    # ── Step 2-3: 获取 + 解析弹幕 ──────────────────────────────
    try:
        raw_xml = fetch_danmaku_raw(cid, cookie=cookie)
        parse_result = parse_xml(raw_xml)
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        lines.append(f'[BiliDanmaku]   弹幕获取失败: {e}')
        return {
            'success': False,
            'summary': '\n'.join(lines),
            'result': None,
            'error': str(e),
            'cid': cid,
        }

    # ── Step 4: 生成摘要 ──────────────────────────────────────
    total = parse_result.total
    skipped = parse_result.skipped

    lines.append(f'[BiliDanmaku]   弹幕获取完成: {total} 条')
    if skipped > 0:
        lines.append(f'[BiliDanmaku]   (跳过 {skipped} 条异常)')

    # 时间范围
    if total > 0:
        first_time = parse_result.items[0].time
        last_time = parse_result.items[-1].time
        lines.append(
            f'[BiliDanmaku]   时间范围: {first_time:.1f}s ~ {last_time:.1f}s'
        )

        # 展示前 5 条弹幕样本
        lines.append(f'[BiliDanmaku]   ── 弹幕样本 (前5条) ──')
        for item in parse_result.items[:5]:
            mode_label = {1: '滚动', 4: '底部', 5: '顶部'}.get(item.mode, f'?')
            lines.append(
                f'[BiliDanmaku]   [{item.time:6.1f}s] [{mode_label}] {item.content}'
            )

        if total > 5:
            lines.append(f'[BiliDanmaku]   ... 还有 {total - 5} 条')
    else:
        lines.append(f'[BiliDanmaku]   (该分段无弹幕)')

    return {
        'success': True,
        'summary': '\n'.join(lines),
        'result': parse_result,
        'error': None,
        'cid': cid,
    }
