// background.js — BiliDanmaku Extension Service Worker (Manifest V3)
// Receives video info from content.js and forwards to Python via Native Messaging.

const LOG_PREFIX = '[BiliDanmaku]';
const NATIVE_HOST_NAME = 'com.bili.danmaku';
const PROGRESS_THROTTLE_MS = 1000; // rate-limit progress updates to 1/s

// ═══════════════════════════════════════════════════════════
// State
// ═══════════════════════════════════════════════════════════

let nativePort = null;
let lastBv = null;
let lastProgressTime = 0;

// ═══════════════════════════════════════════════════════════
// Native Messaging Connection
// ═══════════════════════════════════════════════════════════

function connectNative() {
    console.log(LOG_PREFIX, '正在连接 Native Host:', NATIVE_HOST_NAME);
    try {
        nativePort = chrome.runtime.connectNative(NATIVE_HOST_NAME);
        console.log(LOG_PREFIX, 'Native Host 已连接');

        nativePort.onMessage.addListener((msg) => {
            console.log(LOG_PREFIX, 'Python 回复:', JSON.stringify(msg));
        });

        nativePort.onDisconnect.addListener(() => {
            const lastError = chrome.runtime.lastError;
            console.warn(LOG_PREFIX, 'Native Host 连接断开',
                lastError ? lastError.message : '');
            nativePort = null;

            // [Beta] Attempt reconnection
            attemptReconnect();
        });
    } catch (e) {
        console.error(LOG_PREFIX, 'connectNative 失败:', e.message);
        nativePort = null;
        // [Beta] Attempt reconnection
        attemptReconnect();
    }
}

// [Beta] Simple reconnection with backoff
let reconnectAttempt = 0;
let reconnectTimer = null;
const MAX_BACKOFF_MS = 30000;

function attemptReconnect() {
    if (reconnectTimer) return; // already scheduled

    const delays = [1000, 2000, 4000, 8000, 16000, 30000];
    const delay = delays[Math.min(reconnectAttempt, delays.length - 1)];

    console.log(LOG_PREFIX, `[Beta] 将在 ${delay}ms 后尝试重连 (attempt ${reconnectAttempt + 1})`);
    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        reconnectAttempt++;
        connectNative();
    }, delay);
}

function resetReconnectState() {
    reconnectAttempt = 0;
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
}

// ═══════════════════════════════════════════════════════════
// Message Routing (from content.js)
// ═══════════════════════════════════════════════════════════

function isBilibiliVideoPage(url) {
    if (!url) return false;
    return /^https?:\/\/www\.bilibili\.com\/(video|bangumi)\//.test(url);
}

function sendToNative(type, payload) {
    if (!nativePort) {
        console.warn(LOG_PREFIX, 'Native Host 未连接, 无法发送消息');
        return;
    }
    const msg = {
        protocolVersion: 1,
        id: crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36),
        timestamp: Date.now(),
        type: type,
        payload: payload,
    };
    try {
        nativePort.postMessage(msg);
    } catch (e) {
        console.error(LOG_PREFIX, '发送消息失败:', e.message);
    }
}

chrome.runtime.onMessage.addListener((message, sender) => {
    // Only accept messages from our content script
    if (!message || message.type !== 'video_info') return;
    if (!sender.tab) return;
    if (!isBilibiliVideoPage(message.pageUrl)) return;

    const bv = message.bv;
    const now = Date.now();

    // Detect video switch (BV changed)
    if (bv && bv !== lastBv) {
        console.log(LOG_PREFIX, '视频切换:', lastBv, '→', bv);
        lastBv = bv;
        resetReconnectState();

        sendToNative('video_switch', {
            bv: message.bv,
            cid: message.cid,
            title: message.title,
            duration: message.duration,
            pageUrl: message.pageUrl,
            resolverName: message.resolverName,
            resolverLevel: message.resolverLevel,
            cookies: message.cookies,
        });
        lastProgressTime = now;
        return;
    }

    // Progress update (throttled: max 1/s per BV)
    if (bv && bv === lastBv) {
        if (now - lastProgressTime < PROGRESS_THROTTLE_MS) return;
        lastProgressTime = now;

        sendToNative('progress_update', {
            bv: message.bv,
            progress: message.progress,
            isPlaying: message.isPlaying,
        });
    }
});

// ═══════════════════════════════════════════════════════════
// Lifecycle
// ═══════════════════════════════════════════════════════════

console.log(LOG_PREFIX, 'Service Worker 已启动');
connectNative();

// Re-connect when SW wakes up from suspend (if port is gone)
// Note: In MV3, the SW may be terminated and restarted.
// The top-level code runs again on restart, so connectNative() is called.
// For mid-lifecycle wake-ups where the port was dropped, we rely on
// onDisconnect triggering attemptReconnect().
