// background.js — BiliDanmaku Extension Service Worker (Manifest V3)
// Receives video info from content.js and forwards to Python via Native Messaging.

const LOG_PREFIX = '[BiliDanmaku]';
const NATIVE_HOST_NAME = 'com.bili.danmaku';
const PROGRESS_THROTTLE_MS = 1000; // rate-limit progress updates to 1/s
const STORAGE_KEY = 'biliDanmakuState';
// After 30 min away, treat as a fresh viewing session rather than a resume.
// Covers the case where both the SW and Python were terminated (browser
// restart / long idle) — Python needs a fresh video_switch to load state.
const SESSION_EXPIRY_MS = 30 * 60 * 1000;

// ═══════════════════════════════════════════════════════════
// State
// ═══════════════════════════════════════════════════════════

let nativePort = null;
let lastBv = null;
let lastProgressTime = 0;
// True when the Native Messaging port was freshly established (new Python
// process).  Consumed by the first message to decide whether a matching BV
// still needs a video_switch (Python is stateless and must be seeded).
let nativePortJustConnected = false;
// True once chrome.storage.local.get() has completed.  Messages arriving
// before that are queued in pendingMessages and replayed afterwards.
let storageLoaded = false;
let pendingMessages = [];

// ═══════════════════════════════════════════════════════════
// Native Messaging Connection
// ═══════════════════════════════════════════════════════════

function connectNative() {
    console.log(LOG_PREFIX, '正在连接 Native Host:', NATIVE_HOST_NAME);
    try {
        nativePort = chrome.runtime.connectNative(NATIVE_HOST_NAME);
        nativePortJustConnected = true; // fresh port = new Python process
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
// Persistent State (chrome.storage.local)
// ═══════════════════════════════════════════════════════════

/** Persist lastBv so SW cold-restarts can avoid spurious video_switch. */
function persistState(bv) {
    chrome.storage.local.set({
        [STORAGE_KEY]: { lastBv: bv, lastUpdateTime: Date.now() }
    }).catch(() => {
        // storage may be unavailable in some Chrome configurations
    });
}

/** Recover lastBv from storage on SW cold-start. */
function loadStoredState() {
    chrome.storage.local.get(STORAGE_KEY, (result) => {
        try {
            const data = result[STORAGE_KEY];
            if (data && data.lastBv && data.lastUpdateTime) {
                const age = Date.now() - data.lastUpdateTime;
                if (age < SESSION_EXPIRY_MS) {
                    lastBv = data.lastBv;
                    console.log(LOG_PREFIX,
                        '从 storage 恢复 lastBv:', lastBv,
                        `(age=${Math.round(age / 1000)}s)`);
                } else {
                    console.log(LOG_PREFIX,
                        'storage 中的 lastBv 已过期',
                        `(age=${Math.round(age / 60000)}min), 视为新会话`);
                }
            }
        } catch (e) {
            console.warn(LOG_PREFIX, 'storage 恢复失败:', e.message);
        }
        storageLoaded = true;

        // Replay any messages that arrived before storage was ready
        const queued = pendingMessages;
        pendingMessages = [];
        for (const { message, sender } of queued) {
            routeMessage(message, sender);
        }
    });
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

/**
 * Core message router.
 *
 * Separated from the onMessage listener so that messages queued before
 * chrome.storage.local has loaded can be replayed through the same path.
 *
 * Video-switch logic:
 *   1. BV changed (real switch / first time) → video_switch + persist
 *   2. Same BV + port freshly connected → video_switch (Python is a new
 *      process and needs to be seeded — port reconnect = new Python)
 *   3. Same BV + same session → progress_update (throttled)
 *
 * The nativePortJustConnected flag is consumed (set to false) after the
 * first message that sees it, so subsequent messages in the same session
 * take the progress_update path.
 */
function routeMessage(message, sender) {
    // Only accept messages from our content script
    if (!message || message.type !== 'video_info') return;
    if (!sender || !sender.tab) return;
    if (!isBilibiliVideoPage(message.pageUrl)) return;

    const bv = message.bv;
    const now = Date.now();
    const portIsFresh = nativePortJustConnected;
    nativePortJustConnected = false;

    // ── Video switch: BV changed ─────────────────────────────
    const bvChanged = (bv && bv !== lastBv);

    // ── Video switch: port reconnected (new Python, same BV) ─
    // Python is stateless — a fresh connection means it has no danmaku
    // loaded, so we must re-send video_switch even for the same BV.
    const needsReseed = (bv && bv === lastBv && portIsFresh);

    if (bvChanged || needsReseed) {
        if (bvChanged) {
            console.log(LOG_PREFIX, '视频切换:', lastBv, '→', bv);
        } else {
            console.log(LOG_PREFIX,
                'Native Port 重连 (同 BV=' + bv + '), 重新发送 video_switch');
            resetReconnectState();
        }
        lastBv = bv;
        persistState(bv);

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

    // ── Same BV, same session → progress_update (throttled) ─
    if (bv && bv === lastBv) {
        if (now - lastProgressTime < PROGRESS_THROTTLE_MS) return;
        lastProgressTime = now;

        sendToNative('progress_update', {
            bv: message.bv,
            progress: message.progress,
            isPlaying: message.isPlaying,
        });
    }
}

chrome.runtime.onMessage.addListener((message, sender) => {
    // Queue messages until storage state is loaded (SW cold-start).
    // Once storageLoaded, routeMessage is called directly.
    if (!storageLoaded) {
        pendingMessages.push({ message, sender });
        return;
    }
    routeMessage(message, sender);
});

// ═══════════════════════════════════════════════════════════
// Lifecycle
// ═══════════════════════════════════════════════════════════

console.log(LOG_PREFIX, 'Service Worker 已启动');
loadStoredState();
connectNative();

// Re-connect when SW wakes up from suspend (if port is gone)
// Note: In MV3, the SW may be terminated and restarted.
// The top-level code runs again on restart, so connectNative() is called.
// For mid-lifecycle wake-ups where the port was dropped, we rely on
// onDisconnect triggering attemptReconnect().
