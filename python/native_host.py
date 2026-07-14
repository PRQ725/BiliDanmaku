#!/usr/bin/env python3
# native_host.py — BiliDanmaku Native Messaging Host (MVP v0.1)
# Receives structured video info from browser extension via stdin,
# prints it to stderr for verification, and replies "ok" via stdout.
#
# Protocol: Chrome Native Messaging (4-byte LE length prefix + JSON)
# Dependencies: Python 3.8+ standard library only

import sys
import json
import struct
import traceback

# Message size limit: 1 MB (Chrome Native Messaging standard)
MAX_MESSAGE_BYTES = 1024 * 1024


def read_message():
    """
    Read a single Native Messaging message from stdin.
    Returns parsed JSON dict, or None if stdin is closed.
    """
    raw_len = sys.stdin.buffer.read(4)
    if not raw_len or len(raw_len) < 4:
        return None

    msg_len = struct.unpack('<I', raw_len)[0]
    if msg_len == 0:
        return None
    if msg_len > MAX_MESSAGE_BYTES:
        raise ValueError(f'消息过大: {msg_len} bytes (max {MAX_MESSAGE_BYTES})')

    raw_data = sys.stdin.buffer.read(msg_len)
    if not raw_data or len(raw_data) < msg_len:
        return None

    return json.loads(raw_data.decode('utf-8'))


def send_message(msg):
    """
    Send a Native Messaging message to stdout.
    msg should be a JSON-serializable dict.
    """
    data = json.dumps(msg, ensure_ascii=False).encode('utf-8')
    sys.stdout.buffer.write(struct.pack('<I', len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def handle_message(msg):
    """
    Process a single message from the extension.
    MVP: print structured video info to stderr for verification.
    """
    msg_type = msg.get('type', 'unknown')
    payload = msg.get('payload', {})
    protocol_version = msg.get('protocolVersion', '?')
    msg_id = msg.get('id', '?')

    bv = payload.get('bv', 'N/A')
    cid = payload.get('cid')
    title = payload.get('title', 'N/A')
    duration = payload.get('duration')
    progress = payload.get('progress')
    is_playing = payload.get('isPlaying')
    resolver_name = payload.get('resolverName', '?')
    resolver_level = payload.get('resolverLevel', '?')

    print(f'[BiliDanmaku] ──────────────────────────────────', file=sys.stderr)
    print(f'[BiliDanmaku] 收到消息  id={msg_id}  protocol=v{protocol_version}', file=sys.stderr)
    print(f'[BiliDanmaku]   type: {msg_type}', file=sys.stderr)
    print(f'[BiliDanmaku]   BV:   {bv}', file=sys.stderr)
    print(f'[BiliDanmaku]   CID:  {cid}', file=sys.stderr)
    print(f'[BiliDanmaku]   标题: {title}', file=sys.stderr)

    if duration is not None:
        print(f'[BiliDanmaku]   时长: {duration}s ({duration//60}分{duration%60:.0f}秒)', file=sys.stderr)
    else:
        print(f'[BiliDanmaku]   时长: N/A', file=sys.stderr)

    if progress is not None:
        print(f'[BiliDanmaku]   进度: {progress:.1f}s', file=sys.stderr)
    if is_playing is not None:
        print(f'[BiliDanmaku]   播放中: {"是" if is_playing else "暂停"}', file=sys.stderr)

    print(f'[BiliDanmaku]   Resolver: {resolver_name} (level={resolver_level})', file=sys.stderr)

    # Flag when cid is missing — v0.2+ will handle this via video_info_handler
    if cid is None:
        print(f'[BiliDanmaku]   ⚠ cid 为空, v0.2+ 将由 video_info_handler 调用 API 补全', file=sys.stderr)

    # Send acknowledgment
    send_message({
        'type': 'status',
        'payload': {
            'status': 'ok',
            'message': f'Received {msg_type} for BV={bv}',
        }
    })


def main():
    print('[BiliDanmaku] ========================================', file=sys.stderr)
    print('[BiliDanmaku] Native Host 已启动 (MVP v0.1)', file=sys.stderr)
    print('[BiliDanmaku] 等待浏览器扩展连接...', file=sys.stderr)
    print('[BiliDanmaku] ========================================', file=sys.stderr)

    msg_count = 0
    while True:
        msg = read_message()
        if msg is None:
            print(f'[BiliDanmaku] 连接断开, 已处理 {msg_count} 条消息, 退出', file=sys.stderr)
            break

        msg_count += 1
        try:
            handle_message(msg)
        except Exception as e:
            print(f'[BiliDanmaku] 消息处理异常 (#{msg_count}): {e}', file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            # Reply with error status so extension knows something went wrong
            try:
                send_message({
                    'type': 'status',
                    'payload': {
                        'status': 'error',
                        'message': str(e),
                    }
                })
            except Exception:
                pass
            # Continue — next message may be fine


if __name__ == '__main__':
    main()
