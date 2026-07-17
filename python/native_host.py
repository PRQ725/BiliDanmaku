#!/usr/bin/env python3
# native_host.py — BiliDanmaku Native Messaging Host
# Step 3: QApplication entry point + stdin background thread + dispatcher integration
#
# Architecture (v0.2.x):
#   Main Thread (Qt GUI):  QApplication + overlay modules + DanmakuIntegration
#   Background Thread:     stdin read loop → dispatcher.publish()
#
# Protocol: Chrome Native Messaging (4-byte LE length prefix + JSON)
# Dependencies: Python 3.10+, PyQt6, requests

import sys
import json
import struct
import time
import threading
import traceback
import os
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import pyqtSignal, QObject
from PyQt6.QtWidgets import QApplication

from danmaku_handler import handle_video_switch
from data_dispatcher import dispatcher
from events import EventType, DanmakuLoadedEvent, ProgressUpdatedEvent, VideoUnloadEvent
from overlay.main_window import TransparentOverlay
from overlay.tray_icon import TrayIcon
from overlay.danmaku_queue import DanmakuQueue
from overlay.danmaku_renderer import DanmakuRenderer

# Message size limit: 1 MB (Chrome Native Messaging standard)
MAX_MESSAGE_BYTES = 1024 * 1024

# Log file path — always relative to this script, not CWD
# (Chrome launches native host with unpredictable working directory)
_LOG_DIR = os.path.dirname(os.path.abspath(__file__))
_LOG_FILE = os.path.join(_LOG_DIR, 'native_host.log')


class TeeStderr:
    """Writes to both the original stderr (terminal) and a log file.

    Chrome launches native_host.py as a child process without a console,
    so stderr is discarded. This tee ensures all logs are captured in
    a file regardless of how the process is launched.
    """
    def __init__(self, file_path):
        self._stderr = sys.__stderr__  # keep reference to real stderr
        self._file = open(file_path, 'a', encoding='utf-8')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self._file.write(f'\n{"=" * 60}\n')
        self._file.write(f'===  Session started at {timestamp}\n')
        self._file.write(f'{"=" * 60}\n')
        self._file.flush()

    def write(self, data):
        self._stderr.write(data)
        self._stderr.flush()
        self._file.write(data)
        self._file.flush()

    def flush(self):
        self._stderr.flush()
        self._file.flush()

    def close(self):
        self._file.close()


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

    IMPORTANT: Only call from the stdin reader thread.
    stdout is the Native Messaging channel — never write non-protocol data.
    """
    data = json.dumps(msg, ensure_ascii=False).encode('utf-8')
    sys.stdout.buffer.write(struct.pack('<I', len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


# ── DanmakuIntegration ────────────────────────────────────────────


class DanmakuIntegration(QObject):
    """Coordinates overlay modules via dispatcher events.

    Lives in the Qt GUI thread. Bridges the dispatcher event bus
    (published from background stdin thread) to the overlay rendering
    pipeline (Qt GUI thread).

    Lifecycle:
        - Subscribes to DANMAKU_LOADED and PROGRESS_UPDATED on init.
        - Connects renderer.frame_rendered → _on_frame for tick→enqueue.
        - quit_requested signal bridges background thread → QApplication.quit().

    Thread safety:
        - _on_danmaku_loaded: called from background thread (dispatcher sync callback).
          queue.load() is thread-safe (DanmakuQueue uses internal lock).
        - _on_frame: called from GUI thread (renderer.frame_rendered signal).
          All Qt widget access happens here.
    """

    quit_requested = pyqtSignal()
    """Emitted from background thread to request Qt event loop exit."""

    def __init__(
        self,
        queue: DanmakuQueue,
        renderer: DanmakuRenderer,
        window: TransparentOverlay,
        tray: TrayIcon,
        parent: QObject | None = None,
    ) -> None:
        """Initialize integration coordinator.

        Args:
            queue: DanmakuQueue instance (thread-safe).
            renderer: DanmakuRenderer instance (GUI thread only).
            window: TransparentOverlay instance.
            tray: TrayIcon instance.
            parent: Parent QObject.
        """
        super().__init__(parent)

        self._queue = queue
        self._renderer = renderer
        self._window = window
        self._tray = tray
        self._wall_clock_start: Optional[float] = None

        # ── Video switch coordination ────────────────────────────
        # _on_danmaku_loaded runs in background thread and must NOT
        # call renderer.clear() directly. Instead it sets a flag;
        # _on_frame (GUI thread) checks it and clears safely.
        self._pending_clear: bool = False

        # ── Frame pipeline ──────────────────────────────────────
        # After renderer updates positions + removes OOB each frame,
        # we inject new danmaku from queue and trigger repaint.
        renderer.frame_rendered.connect(self._on_frame)

        # ── Dispatcher subscriptions ─────────────────────────────
        # These callbacks run in the publisher's thread (stdin thread).
        # queue.load() is thread-safe; renderer/widget access must
        # only happen via _on_frame (GUI thread).
        dispatcher.subscribe(EventType.DANMAKU_LOADED, self._on_danmaku_loaded)
        dispatcher.subscribe(EventType.PROGRESS_UPDATED, self._on_progress_updated)
        dispatcher.subscribe(EventType.VIDEO_UNLOAD, self._on_video_unload)

    # ── Dispatcher callbacks (called from background thread) ──────

    def _on_danmaku_loaded(self, event: DanmakuLoadedEvent) -> None:
        """Handle DANMAKU_LOADED: load items into queue, reset wall clock.

        Called synchronously from dispatcher.publish() in the stdin thread.
        queue.load() is thread-safe. renderer.clear() is deferred to
        _on_frame (GUI thread) via _pending_clear flag.

        Video-switch semantic: the old video's danmaku are always invalid,
        regardless of whether the new video's fetch succeeds.  Clearing is
        unconditional — a failed fetch means the screen should be empty,
        not stuck on stale content.
        """
        # Defer renderer clear to GUI thread — must NOT call
        # renderer.clear() here (cross-thread Qt access).
        # Clear is unconditional: old video is always stale.
        self._pending_clear = True

        if event.success:
            self._queue.load(event.items)
            self._wall_clock_start = time.monotonic()
        else:
            # Clear stale queue so old items don't re-enter renderer.
            # wall_clock_start stays None → _on_frame stops ticking.
            self._queue.clear()
            self._wall_clock_start = None

    def _on_progress_updated(self, event: ProgressUpdatedEvent) -> None:
        """Handle PROGRESS_UPDATED: v0.2 no-op.

        Reserved for v0.3+ playback sync integration.
        """
        pass

    def _on_video_unload(self, event: VideoUnloadEvent) -> None:
        """Handle VIDEO_UNLOAD: clear all danmaku state.

        Called synchronously from dispatcher.publish() in the stdin thread
        when the user closes the B站 video tab or navigates away.

        Clears:
            - queue (thread-safe) — all buffered danmaku discarded
            - wall clock — stops _on_frame from ticking new items
            - _pending_clear — triggers renderer.clear() on next _on_frame
        """
        self._pending_clear = True
        self._queue.clear()
        self._wall_clock_start = None

    # ── Frame callback (called from GUI thread) ──────────────────

    def _on_frame(self) -> None:
        """Inject new danmaku from queue into renderer each frame.

        Called from renderer.frame_rendered signal (GUI thread).
        Safe to access all Qt objects.
        """
        # Handle deferred renderer clear (set by _on_danmaku_loaded
        # in background thread on video switch).
        if self._pending_clear:
            self._renderer.clear()
            self._pending_clear = False

        # ── Window visibility ──────────────────────────────────
        # _wall_clock_start is None when no video is active
        # (video_unload, app startup before first video_switch,
        # or failed danmaku fetch).  Hide the overlay so it
        # doesn't linger as an empty transparent sheet on screen.
        if self._wall_clock_start is None:
            if self._window.isVisible():
                self._window.hide()
            return

        # _wall_clock_start is set → active video session.
        # Ensure the overlay is visible (re-show after video_unload
        # or initial show for first video_switch).
        if not self._window.isVisible():
            self._window.show()

        elapsed = time.monotonic() - self._wall_clock_start
        new_items = self._queue.tick(elapsed)
        if new_items:
            self._renderer.enqueue(new_items)

        # Trigger repaint — paintEvent calls renderer.render()
        self._window.update()


# ── Message Handlers (called from background thread) ──────────────


def _handle_video_switch_message(payload: dict) -> None:
    """Process a video_switch message from the extension.

    1. Call danmaku_handler to fetch and parse danmaku (HTTP in background).
    2. Print summary to stderr.
    3. Publish DanmakuLoadedEvent via dispatcher.
    4. Reply to extension via stdout.

    Args:
        payload: The message payload dict from the extension.
    """
    bv = payload.get('bv', '')
    cid = payload.get('cid')
    title = payload.get('title', '')
    resolver_level = payload.get('resolverLevel', 'UNKNOWN')
    cookie = payload.get('cookies', None)

    result = handle_video_switch(
        bv=bv,
        cid=cid,
        title=str(title),
        resolver_level=str(resolver_level),
        cookie=cookie if cookie else None,
    )

    # Log summary
    print(result['summary'], file=sys.stderr)

    # Publish event to dispatcher
    parse_result = result.get('result')
    final_cid = result.get('cid') or 0

    if result['success'] and parse_result is not None:
        event = DanmakuLoadedEvent(
            bv=bv,
            cid=final_cid,
            title=str(title),
            success=True,
            items=parse_result.items,
            total=parse_result.total,
            summary=result['summary'],
        )
    else:
        event = DanmakuLoadedEvent(
            bv=bv,
            cid=final_cid,
            title=str(title),
            success=False,
            error=result.get('error', 'unknown'),
            summary=result['summary'],
        )

    dispatcher.publish(event)

    # Reply via stdout (Native Messaging protocol)
    if result['success']:
        send_message({
            'type': 'status',
            'payload': {
                'status': 'ok',
                'message': f'Danmaku loaded: {parse_result.total if parse_result else 0} items',
            }
        })
    else:
        send_message({
            'type': 'status',
            'payload': {
                'status': 'error',
                'message': result.get('error', 'danmaku fetch failed'),
            }
        })


def _handle_progress_update_message(payload: dict) -> None:
    """Process a progress_update message from the extension.

    Publishes ProgressUpdatedEvent via dispatcher (v0.2 no-op for consumers,
    but event is published for v0.3+ readiness).

    Args:
        payload: The message payload dict from the extension.
    """
    bv = payload.get('bv', '')
    progress = payload.get('progress', 0)
    is_playing = payload.get('isPlaying', False)

    event = ProgressUpdatedEvent(
        bv=bv,
        progress=float(progress) if progress else 0.0,
        is_playing=bool(is_playing),
    )
    dispatcher.publish(event)

    send_message({
        'type': 'status',
        'payload': {
            'status': 'ok',
            'message': f'Received progress_update for BV={bv}',
        }
    })


def _handle_video_unload_message(payload: dict) -> None:
    """Process a video_unload message from the extension.

    Fires when the user closes the B站 video tab or navigates away.
    Publishes VideoUnloadEvent to clear all danmaku state:
    renderer, queue, and wall clock.

    Args:
        payload: The message payload dict (unused — event is metadata-only).
    """
    print('[BiliDanmaku] [lifecycle] 收到 video_unload — 清理渲染状态', file=sys.stderr)
    event = VideoUnloadEvent()
    dispatcher.publish(event)


def handle_message(msg: dict) -> None:
    """Process a single message from the extension.

    Prints structured info to stderr, then dispatches to the
    appropriate handler based on message type.

    Args:
        msg: Parsed JSON message dict from the extension.
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

    # ── Dispatch by message type ──────────────────────────────────
    if msg_type == 'video_switch':
        _handle_video_switch_message(payload)
    elif msg_type == 'progress_update':
        _handle_progress_update_message(payload)
    elif msg_type == 'video_unload':
        _handle_video_unload_message(payload)
    else:
        # Unknown message type — ack anyway
        send_message({
            'type': 'status',
            'payload': {
                'status': 'ok',
                'message': f'Received {msg_type} for BV={bv}',
            }
        })


# ── Stdin Reader Thread ──────────────────────────────────────────


def stdin_reader_loop(integration: DanmakuIntegration) -> None:
    """Background thread: read Native Messaging messages from stdin.

    Runs as a daemon thread. When stdin closes (Chrome disconnects),
    signals the GUI thread to quit via integration.quit_requested.

    Args:
        integration: DanmakuIntegration instance for quit signalling.
    """
    print('[BiliDanmaku] stdin reader thread started', file=sys.stderr)

    msg_count = 0
    last_msg_time = time.monotonic()
    while True:
        msg = None
        try:
            msg = read_message()
            if msg is None:
                idle_sec = time.monotonic() - last_msg_time
                print(
                    f'[BiliDanmaku] 连接断开, 已处理 {msg_count} 条消息, '
                    f'idle={idle_sec:.0f}s, 退出',
                    file=sys.stderr,
                )
                break

            msg_count += 1
            last_msg_time = time.monotonic()
            handle_message(msg)

        except Exception as e:
            msg_count += 1
            print(
                f'[BiliDanmaku] 消息处理异常 (#{msg_count}): {e}',
                file=sys.stderr,
            )
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

    # Signal GUI thread to quit cleanly
    print(
        '[BiliDanmaku] [lifecycle] stdin_reader_loop 退出 → 发送 quit_requested',
        file=sys.stderr,
    )
    integration.quit_requested.emit()


# ── Main Entry Point ─────────────────────────────────────────────


def main() -> None:
    """Application entry point.

    Startup order (must be followed for Qt thread safety):
        1. QApplication          — must be first
        2. TeeStderr             — log everything early
        3. Overlay modules       — window, tray, queue, renderer
        4. Wire render callback  — window.set_renderer(renderer.render)
        5. DanmakuIntegration    — connects dispatcher ↔ overlay
        6. Start renderer        — begin frame loop
        7. Show window + tray
        8. Stdin thread          — begin reading Chrome messages
        9. Qt event loop         — blocks until quit
    """
    # 1. QApplication (must be first — required by all Qt objects)
    app = QApplication(sys.argv)
    app.setApplicationName('BiliDanmaku')
    # Don't quit when overlay window is closed (tray controls lifecycle)
    app.setQuitOnLastWindowClosed(False)

    # 2. TeeStderr — capture all logs to file + terminal
    sys.stderr = TeeStderr(_LOG_FILE)

    print('[BiliDanmaku] ========================================', file=sys.stderr)
    print('[BiliDanmaku] Native Host 已启动 (v0.2.x)', file=sys.stderr)
    print(f'[BiliDanmaku] [lifecycle] PID={os.getpid()} 启动时间={datetime.now().isoformat()}', file=sys.stderr)
    print('[BiliDanmaku] Overlay + Dispatcher 集成模式', file=sys.stderr)
    print('[BiliDanmaku] 等待浏览器扩展连接...', file=sys.stderr)
    print('[BiliDanmaku] ========================================', file=sys.stderr)

    # 3. Overlay modules
    window = TransparentOverlay()
    tray = TrayIcon(parent=app)
    queue = DanmakuQueue()
    renderer = DanmakuRenderer()
    renderer.set_render_area(window.render_area())

    # 4. Wire render callback — paintEvent → renderer.render()
    window.set_renderer(renderer.render)

    # 5. Integration coordinator (subscribes to dispatcher events)
    integration = DanmakuIntegration(queue, renderer, window, tray)
    integration.quit_requested.connect(app.quit)
    # 诊断日志：quit_requested 信号在 GUI 线程被接收时记录
    integration.quit_requested.connect(
        lambda: print('[BiliDanmaku] [lifecycle] quit_requested 信号已接收 → app.quit() 已调用', file=sys.stderr)
    )

    # 6. Start rendering frame loop (~30fps QTimer)
    renderer.start()

    # 7. Show UI
    tray.show()
    window.show()

    # 8. Background stdin reader thread
    stdin_thread = threading.Thread(
        target=stdin_reader_loop,
        args=(integration,),
        daemon=True,
        name='stdin-reader',
    )
    stdin_thread.start()

    # 9. Qt event loop (blocks until QApplication.quit())
    print('[BiliDanmaku] [lifecycle] 进入 Qt 事件循环 (app.exec)', file=sys.stderr)
    exit_code = app.exec()
    print(f'[BiliDanmaku] [lifecycle] app.exec 返回, exit_code={exit_code}', file=sys.stderr)

    # 10. Cleanup — 先隐藏窗口避免残留冻结画面
    print('[BiliDanmaku] [lifecycle] window.hide()', file=sys.stderr)
    window.hide()
    print('[BiliDanmaku] [lifecycle] renderer.stop()', file=sys.stderr)
    renderer.stop()
    print('[BiliDanmaku] [lifecycle] renderer.clear()', file=sys.stderr)
    renderer.clear()
    print(f'[BiliDanmaku] [lifecycle] 进程退出, exit_code={exit_code}', file=sys.stderr)


if __name__ == '__main__':
    main()
