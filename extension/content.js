// content.js — BiliDanmaku Extension
// Injected into Bilibili video/bangumi pages via manifest.json content_scripts.
// Extracts video metadata via Resolver Chain and monitors playback state.

const LOG_PREFIX = '[BiliDanmaku]';

// ═══════════════════════════════════════════════════════════
// Resolver Chain — Multi-strategy video info extraction
// ═══════════════════════════════════════════════════════════

class InitialStateResolver {
    name = 'InitialState';
    level = 'FULL';

    resolve() {
        const state = window.__INITIAL_STATE__;
        if (!state || !state.videoData) return null;
        return {
            bv: state.videoData.bvid,
            cid: state.videoData.cid,
            title: state.videoData.title,
            duration: state.videoData.duration,
        };
    }
}

class UrlRegexResolver {
    name = 'UrlRegex';
    level = 'PARTIAL';

    resolve() {
        const match = location.href.match(/\/video\/(BV[a-zA-Z0-9]+)/);
        if (!match) return null;
        return {
            bv: match[1],
            cid: null,
            title: document.title || null,
            duration: null,
        };
    }
}

class MetaTagResolver {
    name = 'MetaTag';
    level = 'PARTIAL';

    resolve() {
        const metaUrl = document.querySelector('meta[itemprop="url"]');
        if (!metaUrl) return null;
        const content = metaUrl.getAttribute('content');
        if (!content) return null;
        const match = content.match(/BV[a-zA-Z0-9]+/);
        if (!match) return null;
        return {
            bv: match[0],
            cid: null,
            title: document.title || null,
            duration: null,
        };
    }
}

class VideoElementResolver {
    name = 'VideoElement';
    level = 'PARTIAL';

    resolve() {
        const video = document.querySelector('video');
        let bv = null;
        // Try video src first
        if (video && video.src) {
            const match = video.src.match(/BV[a-zA-Z0-9]+/);
            if (match) bv = match[0];
        }
        // Fallback to URL
        if (!bv) {
            const match = location.href.match(/\/video\/(BV[a-zA-Z0-9]+)/);
            if (match) bv = match[1];
        }
        if (!bv) return null;
        return {
            bv: bv,
            cid: null,
            title: document.title || null,
            duration: video ? video.duration || null : null,
        };
    }
}

class VideoInfoResolverChain {
    constructor() {
        // FULL resolvers first, PARTIAL as fallback
        this.resolvers = [
            new InitialStateResolver(),
            new UrlRegexResolver(),
            new MetaTagResolver(),
            new VideoElementResolver(),
        ];
    }

    /** Extract BV from current URL for cross-validation. */
    _getBvFromUrl() {
        const match = location.href.match(/\/video\/(BV[a-zA-Z0-9]+)/);
        return match ? match[1] : null;
    }

    resolve() {
        const urlBv = this._getBvFromUrl();
        console.log(LOG_PREFIX, `Resolver Chain 启动 (URL BV=${urlBv || '?'})`);

        for (const resolver of this.resolvers) {
            try {
                const result = resolver.resolve();
                if (result && result.bv) {
                    // ── Cross-validate against URL BV ─────────────────
                    // During SPA navigation, __INITIAL_STATE__ may still hold
                    // the previous video's data. If the resolver returned a BV
                    // that differs from the URL, the data is stale → skip.
                    if (urlBv && result.bv !== urlBv) {
                        console.warn(
                            LOG_PREFIX,
                            `Resolver ${resolver.name}: BV 不匹配 URL ` +
                            `(resolver=${result.bv}, url=${urlBv})，数据过时，跳过`
                        );
                        continue;
                    }

                    // ── Log result ─────────────────────────────────────
                    console.log(
                        LOG_PREFIX,
                        `Resolver: ${resolver.name} ✓ ` +
                        `(level=${resolver.level}, cid=${result.cid ?? 'null'})`
                    );
                    console.log(
                        LOG_PREFIX,
                        `  提取结果: bv=${result.bv}, title=${result.title || '(null)'}, ` +
                        `duration=${result.duration ?? 'null'}`
                    );

                    result._resolver = resolver.name;
                    result._level = resolver.level;
                    return result;
                }
            } catch (e) {
                console.warn(LOG_PREFIX, `Resolver ${resolver.name} 失败:`, e.message);
            }
        }
        console.error(LOG_PREFIX, '所有 Resolver 均失败');
        return null;
    }
}

// ═══════════════════════════════════════════════════════════
// Playback State Monitor
// ═══════════════════════════════════════════════════════════

class PlaybackMonitor {
    constructor(videoInfo, onRequestRetry) {
        this.bv = videoInfo.bv;
        this.cid = videoInfo.cid;
        this.title = videoInfo.title;
        this.duration = videoInfo.duration;
        this.pageUrl = location.href;
        this.resolverName = videoInfo._resolver || 'unknown';
        this.resolverLevel = videoInfo._level || 'unknown';
        this.onUpdate = null; // set by startExtraction
        this.onRequestRetry = onRequestRetry; // callback to request data refresh
        this.videoElement = null;
        this.pollTimer = null;
        this.lastSentBv = null;

        this._findVideo();
        this._start();
    }

    _findVideo() {
        this.videoElement = document.querySelector('video');
        if (!this.videoElement) {
            console.warn(LOG_PREFIX, '未找到 <video> 元素, 1s后重试');
            setTimeout(() => this._findVideo(), 1000);
        }
    }

    _start() {
        this._sendVideoSwitch(); // first message is always a switch

        if (this.videoElement) {
            this.videoElement.addEventListener('play', () => this._sendUpdate());
            this.videoElement.addEventListener('pause', () => this._sendUpdate());
            this.videoElement.addEventListener('seeked', () => this._sendUpdate());
        }

        // Poll every 1s as fallback + for progress tracking
        this.pollTimer = setInterval(() => this._sendUpdate(), 1000);
    }

    /** Update monitor data after a delayed re-resolution (SPA retry). */
    updateVideoInfo(videoInfo) {
        const oldTitle = this.title;
        this.bv = videoInfo.bv;
        this.cid = videoInfo.cid;
        this.title = videoInfo.title;
        this.duration = videoInfo.duration;
        this.resolverName = videoInfo._resolver || this.resolverName;
        this.resolverLevel = videoInfo._level || this.resolverLevel;
        console.log(
            LOG_PREFIX,
            `Monitor 数据刷新: title="${oldTitle}" → "${this.title}", ` +
            `resolver=${this.resolverName} (${this.resolverLevel})`
        );
        this._sendVideoSwitch(); // notify Python of updated data
    }

    _sendVideoSwitch() {
        const msg = {
            type: 'video_info',
            bv: this.bv,
            cid: this.cid,
            title: this.title || '',
            progress: this.videoElement ? this.videoElement.currentTime : 0,
            duration: this.videoElement ? this.videoElement.duration || this.duration : this.duration,
            isPlaying: this.videoElement ? !this.videoElement.paused : false,
            pageUrl: this.pageUrl,
            resolverName: this.resolverName,
            resolverLevel: this.resolverLevel,
            cookies: document.cookie, // pass B站 cookies for API requests
        };
        this.lastSentBv = this.bv;
        console.log(LOG_PREFIX, `发送 video_switch: bv=${msg.bv}, title="${msg.title}", cookies=${document.cookie ? document.cookie.length + ' chars' : '(none)'}`);
        chrome.runtime.sendMessage(msg).catch(() => {
            // Extension context may not be ready; retry on next poll
        });

        // Schedule retry if PARTIAL (may have stale title from document.title)
        if (this.resolverLevel === 'PARTIAL' && this.onRequestRetry) {
            console.log(LOG_PREFIX, 'PARTIAL resolver, 3s后重试获取完整数据...');
            setTimeout(() => this.onRequestRetry(this), 3000);
        }
    }

    _sendUpdate() {
        if (!this.videoElement) {
            this._findVideo();
            return;
        }
        const progress = this.videoElement.currentTime;
        const isPlaying = !this.videoElement.paused;

        const msg = {
            type: 'video_info',
            bv: this.bv,
            cid: this.cid,
            title: this.title || '',
            progress: progress,
            duration: this.videoElement.duration || this.duration,
            isPlaying: isPlaying,
            pageUrl: this.pageUrl,
            resolverName: this.resolverName,
            resolverLevel: this.resolverLevel,
            cookies: document.cookie,
        };

        // Check if BV changed (video switch detected during poll)
        if (this.lastSentBv && this.lastSentBv !== this.bv) {
            console.log(LOG_PREFIX, '检测到视频切换: ', this.lastSentBv, '→', this.bv);
            this.lastSentBv = this.bv;
        }

        chrome.runtime.sendMessage(msg).catch(() => {});
    }

    destroy() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
    }
}

// ═══════════════════════════════════════════════════════════
// SPA Navigation Detector
// ═══════════════════════════════════════════════════════════

class SpaNavigator {
    constructor(onNavigate) {
        this.onNavigate = onNavigate;
        this.lastHref = location.href;

        // Strategy 1: MutationObserver on <title>
        const titleEl = document.querySelector('title');
        if (titleEl) {
            this.titleObserver = new MutationObserver(() => {
                this._check();
            });
            this.titleObserver.observe(titleEl, { childList: true, subtree: false });
        }

        // Strategy 2: Periodic URL check (fallback)
        this.urlCheckTimer = setInterval(() => this._check(), 2000);
    }

    _check() {
        if (location.href !== this.lastHref) {
            console.log(LOG_PREFIX, 'SPA 导航检测:', this.lastHref, '→', location.href);
            this.lastHref = location.href;
            this.onNavigate();
        }
    }

    destroy() {
        if (this.titleObserver) this.titleObserver.disconnect();
        if (this.urlCheckTimer) clearInterval(this.urlCheckTimer);
    }
}

// ═══════════════════════════════════════════════════════════
// Main Entry
// ═══════════════════════════════════════════════════════════

let currentMonitor = null;
let currentNavigator = null;
let retryTimer = null; // for delayed PARTIAL re-resolution

/**
 * Try to re-resolve video info to improve data quality.
 * Used when initial resolution was PARTIAL (stale title risk).
 * If a better resolver (FULL) succeeds, update the monitor in place.
 */
function attemptDataRefresh(monitor) {
    // Only retry if this monitor is still the current one
    if (monitor !== currentMonitor) return;

    const chain = new VideoInfoResolverChain();
    const videoInfo = chain.resolve();
    if (!videoInfo) return;

    // Only update if we got better data than before
    if (videoInfo._level === 'FULL' || (videoInfo.title && videoInfo.title !== monitor.title)) {
        console.log(LOG_PREFIX, `重试解析获得更好数据 (level=${videoInfo._level})，更新 monitor`);
        monitor.updateVideoInfo(videoInfo);
    }
}

function startExtraction(delayMs) {
    const run = () => {
        const chain = new VideoInfoResolverChain();
        const videoInfo = chain.resolve();

        if (!videoInfo) {
            console.error(LOG_PREFIX, '无法提取视频信息, 2s后重试');
            setTimeout(startExtraction, 2000);
            return;
        }

        // Destroy previous monitor if exists (SPA switch)
        if (currentMonitor) {
            currentMonitor.destroy();
            currentMonitor = null;
        }

        // Clear any pending retry timer
        if (retryTimer) {
            clearTimeout(retryTimer);
            retryTimer = null;
        }

        currentMonitor = new PlaybackMonitor(videoInfo, attemptDataRefresh);
    };

    if (delayMs && delayMs > 0) {
        console.log(LOG_PREFIX, `SPA 导航后延迟 ${delayMs}ms 再解析 (等待页面更新)...`);
        setTimeout(run, delayMs);
    } else {
        run();
    }
}

// Bootstrap
console.log(LOG_PREFIX, 'Content Script 已加载, URL:', location.href);
startExtraction();

// SPA navigation watcher — uses 1s delay to let B站 framework update
// __INITIAL_STATE__ and document.title before we resolve.
currentNavigator = new SpaNavigator(() => {
    console.log(LOG_PREFIX, 'SPA 导航, 重新提取视频信息 (1s延迟)');
    startExtraction(1000);
});
