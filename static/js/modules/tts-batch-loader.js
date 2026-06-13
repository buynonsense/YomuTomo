/**
 * TTS 客户端批量加载器
 *
 * 设计目标：
 * - 一次性把当前文章的所有句子 TTS 拉到本地缓存（IndexedDB），避免逐句网络等待
 * - 缓存跨页面切换不丢失，TTL/容量超出后自动淘汰
 * - 加载过程不阻塞 UI：并发 2 路拉取 + 进度回调
 * - 失败时不中断整体进度：单句失败计入 failCount，但继续后续
 *
 * 存储：IndexedDB yomu-tts 库 / tts-blobs 对象仓库
 *   key: sha1(`${language}|${speed}|${text}`)
 *   value: { blob, mime, bytes, createdAt, lang, speed, text, hits }
 */

(function (global) {
  'use strict';

  // 用 SubtleCrypto 算 sha1；如果浏览器没有（很罕见）回退到简单 hash
  async function sha1Hex(input) {
    try {
      if (global.crypto && global.crypto.subtle && typeof TextEncoder !== 'undefined') {
        const buf = new TextEncoder().encode(input);
        const digest = await global.crypto.subtle.digest('SHA-1', buf);
        const bytes = new Uint8Array(digest);
        let hex = '';
        for (let i = 0; i < bytes.length; i++) {
          hex += bytes[i].toString(16).padStart(2, '0');
        }
        return hex;
      }
    } catch (_) { /* fall through */ }
    // 兜底：djb2 + length，不抗碰撞但够用作 cache key 区分
    let h = 5381;
    for (let i = 0; i < input.length; i++) {
      h = ((h << 5) + h) + input.charCodeAt(i);
      h |= 0;
    }
    return 'fb_' + (h >>> 0).toString(16) + '_' + input.length.toString(16);
  }

  // 注入点：测试可以用 fake-indexeddb 替换 global.indexedDB
  function getIDB() {
    return global.indexedDB;
  }

  const DB_NAME = 'yomu-tts';
  const DB_VERSION = 1;
  const STORE = 'tts-blobs';

  function openDB() {
    return new Promise((resolve, reject) => {
      const idb = getIDB();
      if (!idb) {
        reject(new Error('IndexedDB 不可用'));
        return;
      }
      const req = idb.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = function (event) {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          const store = db.createObjectStore(STORE, { keyPath: 'key' });
          store.createIndex('createdAt', 'createdAt', { unique: false });
        }
        void event;
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error || new Error('IDB open failed')); };
      req.onblocked = function () { reject(new Error('IDB blocked')); };
    });
  }

  function withStore(mode, fn) {
    return openDB().then(function (db) {
      return new Promise(function (resolve, reject) {
        const tx = db.transaction(STORE, mode);
        const store = tx.objectStore(STORE);
        let result;
        try {
          result = fn(store);
        } catch (e) {
          reject(e);
          return;
        }
        tx.oncomplete = function () { resolve(result && result.value !== undefined ? result.value : result); };
        tx.onabort = function () { reject(tx.error || new Error('IDB tx aborted')); };
        tx.onerror = function () { reject(tx.error || new Error('IDB tx error')); };
      }).finally(function () { db.close(); });
    });
  }

  class TtsBatchLoader {
    constructor(options) {
      options = options || {};
      this.ttlMs = options.ttlMs || 7 * 24 * 60 * 60 * 1000; // 7 days
      this.maxEntries = options.maxEntries || 200;
      this.maxBytes = options.maxBytes || 50 * 1024 * 1024;   // 50 MB
      this.concurrency = options.concurrency || 2;
      this.retryPerItem = options.retryPerItem || 1;
      this.fetchTimeoutMs = options.fetchTimeoutMs || 60000;
      this.endpoint = options.endpoint || '/api/tts';
    }

    /**
     * 把一项写入缓存
     * @param {string} text
     * @param {Blob} blob
     * @param {{language?:string, speed?:number}} options
     */
    put(text, blob, options) {
      const language = (options && options.language) || 'JP';
      const speed = (options && typeof options.speed === 'number') ? options.speed : 1.0;
      return sha1Hex(`${language}|${speed}|${text}`).then(function (key) {
        const record = {
          key: key,
          text: text,
          language: language,
          speed: speed,
          blob: blob,
          mime: blob.type || 'audio/wav',
          bytes: blob.size || 0,
          createdAt: Date.now(),
          hits: 0
        };
        return withStore('readwrite', function (store) {
          store.put(record);
        });
      });
    }

    /**
     * 取缓存命中。命中返回 {blob, language, speed}，未命中返回 null。
     * 命中会异步增加 hits；TTL 过期视为未命中并删除。
     */
    get(text, options) {
      const self = this;
      const language = (options && options.language) || 'JP';
      const speed = (options && typeof options.speed === 'number') ? options.speed : 1.0;
      return sha1Hex(`${language}|${speed}|${text}`).then(function (key) {
        return withStore('readwrite', function (store) {
          return new Promise(function (resolve, reject) {
            const req = store.get(key);
            req.onsuccess = function () {
              const rec = req.result;
              if (!rec) { resolve(null); return; }
              if (Date.now() - rec.createdAt > self.ttlMs) {
                try { store.delete(key); } catch (_) { /* ignore */ }
                resolve(null);
                return;
              }
              // 命中：递增 hits（异步，错误不影响返回）
              try {
                rec.hits = (rec.hits || 0) + 1;
                store.put(rec);
              } catch (_) { /* ignore */ }
              resolve({ blob: rec.blob, language: rec.language, speed: rec.speed });
            };
            req.onerror = function () { reject(req.error); };
          });
        });
      });
    }

    /** 手动清空缓存（清空整个 tts-blobs 仓库） */
    clear() {
      return withStore('readwrite', function (store) {
        store.clear();
      });
    }

    /** 统计：{ count, totalBytes, oldestCreatedAt } */
    stats() {
      return withStore('readonly', function (store) {
        return new Promise(function (resolve, reject) {
          const out = { count: 0, totalBytes: 0, oldestCreatedAt: null };
          const req = store.openCursor();
          req.onsuccess = function () {
            const cur = req.result;
            if (!cur) { resolve(out); return; }
            out.count += 1;
            out.totalBytes += (cur.value && cur.value.bytes) || 0;
            if (out.oldestCreatedAt == null || (cur.value && cur.value.createdAt < out.oldestCreatedAt)) {
              out.oldestCreatedAt = cur.value ? cur.value.createdAt : null;
            }
            cur.continue();
          };
          req.onerror = function () { reject(req.error); };
        });
      });
    }

    /**
     * TTL + 容量淘汰
     *  1. 删除 createdAt < now - ttlMs 的所有项
     *  2. 如果 count > maxEntries 或 totalBytes > maxBytes，按 createdAt 升序删除直到满足上限
     */
    evict() {
      const self = this;
      return withStore('readwrite', function (store) {
        return new Promise(function (resolve, reject) {
          const expiredKeys = [];
          const all = [];
          const req = store.openCursor();
          req.onsuccess = function () {
            const cur = req.result;
            if (!cur) {
              // 1) 删过期
              expiredKeys.forEach(function (k) { try { store.delete(k); } catch (_) { /* ignore */ } });
              // 2) 按容量淘汰
              const remaining = all.filter(function (r) { return expiredKeys.indexOf(r.key) === -1; });
              remaining.sort(function (a, b) { return a.createdAt - b.createdAt; });
              let totalBytes = remaining.reduce(function (s, r) { return s + (r.bytes || 0); }, 0);
              let i = 0;
              while ((remaining.length - i > self.maxEntries) || (totalBytes > self.maxBytes)) {
                if (i >= remaining.length) break;
                const victim = remaining[i];
                try { store.delete(victim.key); } catch (_) { /* ignore */ }
                totalBytes -= (victim.bytes || 0);
                i += 1;
              }
              resolve({ removed: expiredKeys.length + i });
              return;
            }
            const rec = cur.value;
            if (!rec) { cur.continue(); return; }
            if (Date.now() - rec.createdAt > self.ttlMs) {
              expiredKeys.push(rec.key);
            } else {
              all.push({ key: rec.key, createdAt: rec.createdAt || 0, bytes: rec.bytes || 0 });
            }
            cur.continue();
          };
          req.onerror = function () { reject(req.error); };
        });
      });
    }

    /**
     * 批量加载。
     * @param {Array<{key:string,text:string}>} items
     * @param {{language?:string, speed?:number, onProgress?:Function, signal?:AbortSignal}} options
     * @returns {Promise<{total:number, ok:number, fail:number, skipped:number, results:Array<{key:string,status:'hit'|'fetched'|'failed'|'skipped', error?:string}>}>}
     */
    loadAll(items, options) {
      options = options || {};
      const self = this;
      const language = options.language || 'JP';
      const speed = typeof options.speed === 'number' ? options.speed : 1.0;
      const onProgress = options.onProgress;
      const signal = options.signal;

      const list = (items || []).filter(function (it) { return it && it.text && String(it.text).trim(); });
      const total = list.length;
      const results = new Array(total);
      let cursor = 0;
      let ok = 0;
      let fail = 0;
      let skipped = 0;

      function emitProgress() {
        if (typeof onProgress === 'function') {
          try {
            onProgress({ done: ok + fail + skipped, total: total, ok: ok, fail: fail, skipped: skipped });
          } catch (_) { /* ignore */ }
        }
      }

      function worker() {
        if (signal && signal.aborted) return Promise.resolve();
        const i = cursor++;
        if (i >= list.length) return Promise.resolve();
        return processOne(i).then(function () {
          if (cursor < list.length) return worker();
          return null;
        });
      }

      function processOne(i) {
        const item = list[i];
        return self.get(item.text, { language: language, speed: speed }).then(function (cached) {
          if (cached) {
            results[i] = { key: item.key, status: 'hit' };
            skipped += 1;
            emitProgress();
            return null;
          }
          return fetchAndStore(item).then(function (status) {
            results[i] = { key: item.key, status: status };
            if (status === 'fetched') ok += 1; else fail += 1;
            emitProgress();
          });
        }).catch(function (err) {
          results[i] = { key: item.key, status: 'failed', error: err && err.message ? err.message : String(err) };
          fail += 1;
          emitProgress();
        });
      }

      function fetchAndStore(item) {
        let attempt = 0;
        const maxAttempt = 1 + self.retryPerItem;
        function tryOnce() {
          attempt += 1;
          return self._fetchBlob(item.text, { language: language, speed: speed, signal: signal })
            .then(function (blob) {
              return self.put(item.text, blob, { language: language, speed: speed })
                .then(function () { return 'fetched'; });
            })
            .catch(function (err) {
              if (attempt < maxAttempt && !(err && err.name === 'AbortError')) {
                return tryOnce();
              }
              throw err;
            });
        }
        return tryOnce();
      }

      // 启动前先淘汰过期/超额
      return this.evict().then(function () {
        emitProgress();
        // 启动 concurrency 个 worker
        const workers = [];
        const n = Math.min(self.concurrency, total);
        for (let i = 0; i < n; i++) workers.push(worker());
        return Promise.all(workers).then(function () {
          return {
            total: total,
            ok: ok,
            fail: fail,
            skipped: skipped,
            results: results
          };
        });
      });
    }

    /** 拉取单个 TTS WAV blob（可被 batch 内部使用，也可被外部独立调用） */
    _fetchBlob(text, opts) {
      const body = { text: text };
      if (opts && typeof opts.speed === 'number') body.speed = opts.speed;
      if (opts && opts.language) body.language = opts.language;

      const controller = new AbortController();
      let timeoutId = null;
      const signal = opts && opts.signal;
      if (signal) {
        if (signal.aborted) {
          const e = new Error('aborted');
          e.name = 'AbortError';
          return Promise.reject(e);
        }
        signal.addEventListener('abort', function () { try { controller.abort(); } catch (_) { /* ignore */ } });
      }
      if (this.fetchTimeoutMs > 0) {
        timeoutId = setTimeout(function () {
          try { controller.abort(); } catch (_) { /* ignore */ }
        }, this.fetchTimeoutMs);
      }

      return fetch(this.endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal
      }).then(function (resp) {
        if (!resp.ok) {
          return resp.text().then(function (txt) {
            const err = new Error(`HTTP ${resp.status} ${txt || ''}`.slice(0, 200));
            err.status = resp.status;
            throw err;
          });
        }
        return resp.blob();
      }).finally(function () {
        if (timeoutId) clearTimeout(timeoutId);
      });
    }
  }

  TtsBatchLoader.sha1Hex = sha1Hex;
  TtsBatchLoader.DB_NAME = DB_NAME;
  TtsBatchLoader.STORE = STORE;

  global.TtsBatchLoader = TtsBatchLoader;
})(typeof window !== 'undefined' ? window : globalThis);
