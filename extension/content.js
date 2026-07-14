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
            title: document.title,
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
            title: document.title,
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
            title: document.title,
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

    resolve() {
        for (const resolver of this.resolvers) {
            try {
                const result = resolver.resolve();
                if (result && result.bv) {
                    console.log(
                        LOG_PREFIX,
                        `Resolver: ${resolver.name} ✓ (level=${resolver.level}, cid=${result.cid ?? 'null'})`
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
    constructor(videoInfo, onUpdate) {
        this.bv = videoInfo.bv;
        this.cid = videoInfo.cid;
        this.title = videoInfo.title;
        this.duration = videoInfo.duration;
        this.pageUrl = location.href;
        this.resolverName = videoInfo._resolver || 'unknown';
        this.resolverLevel = videoInfo._level || 'unknown';
        this.onUpdate = onUpdate;
        this.videoElement = null;
        this.pollTimer = null;
        this.lastSentBv = null; // to track video_switch vs progress_update

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

    _sendVideoSwitch() {
        const msg = {
            type: 'video_info',
            bv: this.bv,
            cid: this.cid,
            title: this.title,
            progress: this.videoElement ? this.videoElement.currentTime : 0,
            duration: this.videoElement ? this.videoElement.duration || this.duration : this.duration,
            isPlaying: this.videoElement ? !this.videoElement.paused : false,
            pageUrl: this.pageUrl,
            resolverName: this.resolverName,
            resolverLevel: this.resolverLevel,
        };
        this.lastSentBv = this.bv;
        console.log(LOG_PREFIX, '发送 video_switch:', msg.bv, msg.title);
        chrome.runtime.sendMessage(msg).catch(() => {
            // Extension context may not be ready; retry on next poll
        });
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
            title: this.title,
            progress: progress,
            duration: this.videoElement.duration || this.duration,
            isPlaying: isPlaying,
            pageUrl: this.pageUrl,
            resolverName: this.resolverName,
            resolverLevel: this.resolverLevel,
        };

        // Check if BV changed (video switch)
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

function startExtraction() {
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

    currentMonitor = new PlaybackMonitor(videoInfo);
}

// Bootstrap
console.log(LOG_PREFIX, 'Content Script 已加载, URL:', location.href);
startExtraction();

// SPA navigation watcher
currentNavigator = new SpaNavigator(() => {
    console.log(LOG_PREFIX, 'SPA 导航, 重新提取视频信息');
    startExtraction();
});
