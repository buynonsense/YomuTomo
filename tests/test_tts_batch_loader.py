"""
TTS 批量加载器 (tts-batch-loader.js) 的 Node VM 测试

通过 vm 跑 static/js/modules/tts-batch-loader.js，注入一个最小可用的内存 IndexedDB
shim（只实现 batch loader 用到的子集：open / objectStore / get / put / delete /
clear / openCursor / onupgradeneeded），以及一个 mock fetch。
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "static" / "js" / "modules" / "tts-batch-loader.js"


def _make_idb_shim_js() -> str:
    return r"""
class IDBRequest {
  constructor() { this.onsuccess = null; this.onerror = null; this.result = undefined; this.error = null; }
  _fire_ok(v) { this.result = v; if (typeof this.onsuccess === 'function') this.onsuccess({ target: this }); }
  _fire_err(e) { this.error = e; if (typeof this.onerror === 'function') this.onerror({ target: this }); }
}

class FakeStore {
  constructor(name, keyPath, sharedRecords) {
    this.name = name;
    this.keyPath = keyPath;
    this.records = sharedRecords || new Map();
  }
  get(key) {
    const r = new IDBRequest();
    setTimeout(() => r._fire_ok(this.records.get(key) || undefined), 0);
    return r;
  }
  put(record) {
    const r = new IDBRequest();
    const self = this;
    setTimeout(() => { self.records.set(record[self.keyPath], record); r._fire_ok(record); }, 0);
    return r;
  }
  delete(key) {
    const r = new IDBRequest();
    setTimeout(() => { this.records.delete(key); r._fire_ok(undefined); }, 0);
    return r;
  }
  clear() {
    const r = new IDBRequest();
    setTimeout(() => { this.records.clear(); r._fire_ok(undefined); }, 0);
    return r;
  }
  openCursor() {
    const r = new IDBRequest();
    const values = Array.from(this.records.values());
    let i = 0;
    const cursor = {
      get value() { return i < values.length ? values[i] : undefined; },
      continue() { i += 1; r._fire_ok(i < values.length ? cursor : null); }
    };
    setTimeout(() => r._fire_ok(values.length > 0 ? cursor : null), 0);
    return r;
  }
}

class FakeTx {
  constructor(store) {
    this.store = store;
    this.objectStore = function() { return store; };
    this.oncomplete = null; this.onabort = null; this.onerror = null; this.error = null;
    // 简化：让 oncomplete 在下一拍触发，模拟事务自然结束
    setTimeout(() => {
      if (typeof this.oncomplete === 'function') this.oncomplete({ target: this });
    }, 5);
  }
}

class FakeDB {
  constructor(records) {
    this.objectStoreNames = { contains: (n) => n === 'tts-blobs' };
    this._store = new FakeStore('tts-blobs', 'key', records);
  }
  transaction() { return new FakeTx(this._store); }
  objectStore() { return this._store; }
  close() {}
}

class IDBOpenRequest {
  constructor() {
    this.onsuccess = null; this.onerror = null; this.onupgradeneeded = null; this.onblocked = null;
    this.result = undefined;
  }
}

const SHARED_RECORDS = new Map();
const indexedDB = {
  open() {
    const req = new IDBOpenRequest();
    setTimeout(() => {
      const db = new FakeDB(SHARED_RECORDS);
      req.result = db;
      if (req.onupgradeneeded) req.onupgradeneeded({ target: req });
      if (req.onsuccess) req.onsuccess({ target: req });
    }, 0);
    return req;
  }
};
globalThis.__resetIdb = () => SHARED_RECORDS.clear();
"""


def _run_in_context(extra_body: str) -> str:
    # extra_body 通常长这样: "(async () => { ... })();"
    # 我们手动拆开 IIFE 以便统一追加 .then / .catch，再插入额外日志
    body = extra_body.strip()
    prefix = "(async () => {"
    suffix = "})();"
    if body.startswith(prefix) and body.endswith(suffix):
        inner = body[len(prefix):-len(suffix)]
    else:
        inner = body
    shim = _make_idb_shim_js()
    script = textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        const code = fs.readFileSync({str(MODULE_PATH)!r}, 'utf8');
        const sandbox = {{
          console: console,
          Intl: Intl,
          TextEncoder: TextEncoder,
          crypto: globalThis.crypto,
        }};
        sandbox.globalThis = sandbox;
        vm.createContext(sandbox);
        sandbox.AbortController = AbortController;
        sandbox.AbortSignal = AbortSignal;
        sandbox.setTimeout = setTimeout;
        sandbox.clearTimeout = clearTimeout;
        {shim}
        sandbox.indexedDB = indexedDB;
        sandbox.fetch = (...args) => globalThis.__fetch(...args);
        globalThis.__setFetch = (fn) => {{ globalThis.__fetch = fn; }};
        process.on('unhandledRejection', () => {{}});
        vm.runInContext(code, sandbox);
        const Loader = sandbox.TtsBatchLoader;
        __resetIdb();
        (async () => {{
          {inner}
        }})().then(() => process.exit(0)).catch((e) => {{ console.error('IIFE ERR', e && e.stack || e); process.exit(1); }});
        """
    )
    completed = subprocess.run(
        ["node", "--unhandled-rejections=warn", "-e", script],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if completed.returncode != 0:
        sys.stderr.write(f"NODE STDERR:\n{completed.stderr}\n")
        sys.stderr.write(f"NODE STDOUT:\n{completed.stdout}\n")
        sys.stderr.flush()
        raise RuntimeError(f"node exited with code {completed.returncode}")
    return completed.stdout


def test_load_all_concurrent_writes_to_idb():
    extra = textwrap.dedent(
        r"""
        (async () => {
          const fetches = [
            { text: 'こんにちは', bytes: 'a' },
            { text: 'さようなら', bytes: 'bb' },
            { text: 'おはよう', bytes: 'ccc' },
          ];
          globalThis.__setFetch(async (url, init) => {
            const body = JSON.parse(init.body);
            const item = fetches.find((f) => f.text === body.text);
            return {
              ok: true,
              status: 200,
              blob: async () => new Blob([item.bytes], { type: 'audio/wav' }),
              text: async () => '',
            };
          });
          const loader = new Loader({ concurrency: 2 });
          const items = fetches.map((f, i) => ({ key: 'k' + i, text: f.text }));
          const result = await loader.loadAll(items, { language: 'JP', speed: 1.0 });
          const stats = await loader.stats();
          console.log('SUMMARY=' + JSON.stringify(result));
          console.log('STATS=' + JSON.stringify(stats));
        })();
        """
    )
    out = _run_in_context(extra)
    summary = json.loads(next(l for l in out.splitlines() if l.startswith("SUMMARY=")).split("=", 1)[1])
    stats = json.loads(next(l for l in out.splitlines() if l.startswith("STATS=")).split("=", 1)[1])
    assert summary["total"] == 3
    assert summary["ok"] == 3
    assert summary["fail"] == 0
    assert summary["skipped"] == 0
    assert all(r["status"] == "fetched" for r in summary["results"])
    assert stats["count"] == 3
    assert stats["totalBytes"] == 6


def test_second_load_hits_cache_and_skips_network():
    extra = textwrap.dedent(
        r"""
        (async () => {
          let networkCalls = 0;
          globalThis.__setFetch(async () => {
            networkCalls += 1;
            return {
              ok: true, status: 200,
              blob: async () => new Blob(['x'], { type: 'audio/wav' }),
              text: async () => '',
            };
          });
          const loader = new Loader();
          const items = [{ key: 'k1', text: '同一句' }];
          const first = await loader.loadAll(items);
          const second = await loader.loadAll(items);
          console.log('FIRST=' + JSON.stringify(first));
          console.log('SECOND=' + JSON.stringify(second));
          console.log('NETCALLS=' + networkCalls);
        })();
        """
    )
    out = _run_in_context(extra)
    first = json.loads(next(l for l in out.splitlines() if l.startswith("FIRST=")).split("=", 1)[1])
    second = json.loads(next(l for l in out.splitlines() if l.startswith("SECOND=")).split("=", 1)[1])
    network_calls = int(next(l for l in out.splitlines() if l.startswith("NETCALLS=")).split("=", 1)[1])
    assert first["ok"] == 1 and first["skipped"] == 0
    assert second["ok"] == 0 and second["skipped"] == 1
    assert network_calls == 1, "第二次应直接命中缓存，不再 fetch"


def test_network_failure_is_recorded_and_continues():
    extra = textwrap.dedent(
        r"""
        (async () => {
          globalThis.__setFetch(async () => ({
            ok: false, status: 500, blob: async () => new Blob(), text: async () => 'boom',
          }));
          const loader = new Loader({ retryPerItem: 0, concurrency: 1 });
          const items = [
            { key: 'a', text: 'A' },
            { key: 'b', text: 'B' },
          ];
          const r = await loader.loadAll(items);
          console.log('RESULT=' + JSON.stringify(r));
        })();
        """
    )
    out = _run_in_context(extra)
    result = json.loads(next(l for l in out.splitlines() if l.startswith("RESULT=")).split("=", 1)[1])
    assert result["total"] == 2
    assert result["fail"] == 2
    assert result["ok"] == 0
    assert all(r["status"] == "failed" for r in result["results"])


def test_evict_drops_expired_entries():
    extra = textwrap.dedent(
        r"""
        (async () => {
          const loader = new Loader({ ttlMs: 10, maxEntries: 100, maxBytes: 10 * 1024 * 1024 });
          await loader.put('a', new Blob(['aaa'], { type: 'audio/wav' }));
          await loader.put('b', new Blob(['bbb'], { type: 'audio/wav' }));
          await new Promise((r) => setTimeout(r, 30));
          await loader.put('c', new Blob(['c'], { type: 'audio/wav' }));
          const evicted = await loader.evict();
          const stats = await loader.stats();
          console.log('EVICT=' + JSON.stringify(evicted));
          console.log('STATS=' + JSON.stringify(stats));
        })();
        """
    )
    out = _run_in_context(extra)
    evicted = json.loads(next(l for l in out.splitlines() if l.startswith("EVICT=")).split("=", 1)[1])
    stats = json.loads(next(l for l in out.splitlines() if l.startswith("STATS=")).split("=", 1)[1])
    assert evicted["removed"] == 2
    assert stats["count"] == 1


def test_capacity_cap_evicts_oldest_first():
    extra = textwrap.dedent(
        r"""
        (async () => {
          const loader = new Loader({ ttlMs: 60_000, maxEntries: 2, maxBytes: 8 });
          await loader.put('a', new Blob(['aaaa']));
          await new Promise((r) => setTimeout(r, 5));
          await loader.put('b', new Blob(['bbbb']));
          await new Promise((r) => setTimeout(r, 5));
          await loader.put('c', new Blob(['cccc']));
          // loadAll 才会触发容量淘汰；put 不自动淘汰
          const r = await loader.loadAll([{ key: 'a', text: 'a' }]);
          console.log('LOAD=' + JSON.stringify(r));
          const stats = await loader.stats();
          const gotA = await loader.get('a');
          const gotB = await loader.get('b');
          const gotC = await loader.get('c');
          console.log('STATS=' + JSON.stringify(stats));
          console.log('A=' + (gotA ? 'hit' : 'miss'));
          console.log('B=' + (gotB ? 'hit' : 'miss'));
          console.log('C=' + (gotC ? 'hit' : 'miss'));
        })();
        """
    )
    out = _run_in_context(extra)
    stats = json.loads(next(l for l in out.splitlines() if l.startswith("STATS=")).split("=", 1)[1])
    a = next(l for l in out.splitlines() if l.startswith("A=")).split("=", 1)[1]
    b = next(l for l in out.splitlines() if l.startswith("B=")).split("=", 1)[1]
    c = next(l for l in out.splitlines() if l.startswith("C=")).split("=", 1)[1]
    assert stats["count"] == 2
    assert a == "miss"
    assert b == "hit"
    assert c == "hit"


def test_clear_empties_store():
    extra = textwrap.dedent(
        r"""
        (async () => {
          const loader = new Loader();
          await loader.put('a', new Blob(['x']));
          await loader.put('b', new Blob(['y']));
          await loader.clear();
          const stats = await loader.stats();
          console.log('COUNT=' + stats.count);
        })();
        """
    )
    out = _run_in_context(extra)
    count = int(next(l for l in out.splitlines() if l.startswith("COUNT=")).split("=", 1)[1])
    assert count == 0
