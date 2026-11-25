import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

IPC_ADDITION = r"""
    // Antigravity Quota Viewer: read-only local LS quota summary query
    localOnly('quota:get-status', async () => {
        const https = require('node:https');
        const { getActiveLsPort, getActiveLsCsrfToken } = require('./authBootstrap');
        const port = getActiveLsPort();
        const csrfToken = getActiveLsCsrfToken();
        if (!port || !csrfToken) {
            return { ok: false, error: 'Language server not ready' };
        }
        const callLs = (rpcPath) => new Promise((resolve) => {
            let settled = false;
            const done = (val) => { if (!settled) { settled = true; resolve(val); } };
            const timer = setTimeout(() => done({ ok: false, error: 'Timeout' }), 8000);
            timer.unref?.();
            const req = https.request({
                hostname: '127.0.0.1',
                port,
                path: rpcPath,
                method: 'POST',
                rejectUnauthorized: false,
                agent: false,
                headers: {
                    'content-type': 'application/json',
                    'connect-protocol-version': '1',
                    'x-codeium-csrf-token': csrfToken,
                    'content-length': '2',
                },
            }, (res) => {
                const chunks = [];
                res.on('data', (c) => chunks.push(c));
                res.on('end', () => {
                    clearTimeout(timer);
                    try {
                        const raw = Buffer.concat(chunks).toString('utf8');
                        if (res.statusCode !== 200) {
                            return done({ ok: false, error: `HTTP ${res.statusCode}` });
                        }
                        done({ ok: true, data: JSON.parse(raw) });
                    } catch (e) {
                        done({ ok: false, error: String(e) });
                    }
                });
            });
            req.on('error', (e) => { clearTimeout(timer); done({ ok: false, error: String(e) }); });
            req.write('{}');
            req.end();
        });
        return await callLs('/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary');
    });
"""

PRELOAD_QUOTA_WIDGET = r"""
// Antigravity Chat Input Quota Viewer
(function() {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  if (window.__agyQuotaViewerInitialized) return;
  window.__agyQuotaViewerInitialized = true;

  const ipc = electron_1 && electron_1.ipcRenderer;
  if (!ipc || typeof ipc.invoke !== 'function') return;

  let cachedModels = [];
  let lastError = '';
  let isLoading = false;
  let activeAnchorBtn = null;
  let popoverEl = null;

  function ensureStyles() {
    if (document.getElementById('agy-quota-style')) return;
    const style = document.createElement('style');
    style.id = 'agy-quota-style';
    style.textContent = `
      .agy-quota-pill {
        display: inline-flex;
        align-items: center;
        align-self: center;
        gap: 4px;
        height: 24px;
        padding: 0 9px;
        margin-left: 6px;
        border-radius: 9999px;
        font-size: 12px;
        font-weight: 500;
        line-height: 1;
        cursor: pointer;
        user-select: none;
        border: 1px solid rgba(255, 255, 255, 0.14);
        background: rgba(255, 255, 255, 0.06);
        color: #9ca3af;
        transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease, transform 0.1s ease;
        flex-shrink: 0;
      }
      .agy-quota-pill:hover { filter: brightness(1.12); }
      .agy-quota-pill:active { transform: scale(0.97); }
      .agy-quota-pill[data-level="ok"] {
        border-color: rgba(16, 185, 129, 0.30);
        background: rgba(16, 185, 129, 0.14);
        color: #34d399;
      }
      .agy-quota-pill[data-level="warn"] {
        border-color: rgba(245, 158, 11, 0.34);
        background: rgba(245, 158, 11, 0.15);
        color: #fbbf24;
      }
      .agy-quota-pill[data-level="low"] {
        border-color: rgba(239, 68, 68, 0.36);
        background: rgba(239, 68, 68, 0.16);
        color: #f87171;
      }
      .agy-quota-popover {
        position: fixed;
        z-index: 2147483647;
        width: 340px;
        background: #18181b;
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 12px;
        box-shadow: 0 14px 36px rgba(0, 0, 0, 0.62);
        padding: 14px 16px;
        color: #f4f4f5;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 13px;
      }
      .agy-quota-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding-bottom: 10px;
        margin-bottom: 12px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      }
      .agy-quota-title { font-size: 14px; font-weight: 600; color: #f4f4f5; }
      .agy-quota-refresh {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 26px;
        height: 26px;
        border-radius: 6px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        background: rgba(255, 255, 255, 0.04);
        color: #a1a1aa;
        cursor: pointer;
        transition: background-color 0.15s ease, color 0.15s ease;
      }
      .agy-quota-refresh:hover { background: rgba(255, 255, 255, 0.10); color: #f4f4f5; }
      .agy-quota-refresh.spinning svg { animation: agyQuotaSpin 0.8s linear infinite; }
      @keyframes agyQuotaSpin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
      }
      .agy-quota-list {
        display: flex;
        flex-direction: column;
        gap: 12px;
        max-height: 280px;
        overflow-y: auto;
      }
      .agy-quota-group-title {
        font-size: 11.5px;
        font-weight: 600;
        color: #71717a;
        margin-top: 4px;
        margin-bottom: -4px;
      }
      .agy-quota-row { display: flex; flex-direction: column; gap: 6px; }
      .agy-quota-row-top {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        font-size: 12.5px;
      }
      .agy-quota-model-name {
        color: #e4e4e7;
        font-weight: 500;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .agy-quota-model-meta {
        color: #a1a1aa;
        font-size: 12px;
        white-space: nowrap;
        flex-shrink: 0;
      }
      .agy-quota-bar-track {
        width: 100%;
        height: 4px;
        border-radius: 9999px;
        background: rgba(255, 255, 255, 0.09);
        overflow: hidden;
      }
      .agy-quota-bar-fill {
        height: 100%;
        border-radius: 9999px;
        transition: width 0.25s ease;
      }
      .agy-quota-empty {
        color: #a1a1aa;
        font-size: 12.5px;
        text-align: center;
        padding: 12px 0;
      }
    `;
    (document.head || document.documentElement).appendChild(style);
  }

  function getLevel(pct) {
    if (pct === null || pct === undefined || Number.isNaN(pct)) return 'idle';
    if (pct > 50) return 'ok';
    if (pct >= 20) return 'warn';
    return 'low';
  }

  function getBarColor(pct) {
    if (pct > 50) return '#10b981';
    if (pct >= 20) return '#f59e0b';
    return '#ef4444';
  }

  function formatResetTime(resetTimeStr, pct) {
    if (pct >= 100) return '已满额';
    if (!resetTimeStr) return '待重置';
    const ts = Date.parse(resetTimeStr);
    if (Number.isNaN(ts)) return '待重置';
    const diffMs = ts - Date.now();
    if (diffMs <= 0) return '即将重置';
    const totalMin = Math.ceil(diffMs / 60000);
    const days = Math.floor(totalMin / 1440);
    const hours = Math.floor((totalMin % 1440) / 60);
    const mins = totalMin % 60;
    if (days > 0) return `${days}天 ${hours}小时后重置`;
    if (hours > 0) return `${hours}小时 ${mins}分钟后重置`;
    return `${mins}分钟后重置`;
  }

  function formatGroupName(name) {
    const raw = (name || '').trim();
    if (/gemini/i.test(raw)) return 'Gemini 模型';
    if (/claude|gpt/i.test(raw)) return 'Claude 与 GPT 模型';
    return raw || '模型配额';
  }

  function formatBucketName(bucket) {
    const raw = `${bucket.displayName || ''} ${bucket.window || ''} ${bucket.bucketId || ''}`.trim();
    if (/5|five/i.test(raw)) return '5 小时限额';
    if (/week/i.test(raw)) return '每周限额';
    return (bucket.displayName || '限额').trim();
  }

  function parseModels(data) {
    const items = [];
    const summary = data?.response || data?.summary?.response || data?.summary || data;
    const groups = Array.isArray(summary?.groups) ? summary.groups : [];
    for (const g of groups) {
      if (!g || !Array.isArray(g.buckets)) continue;
      const gLabel = formatGroupName(g.displayName);
      const groupItems = [];
      for (const b of g.buckets) {
        if (!b || b.disabled) continue;
        const frac = typeof b.remainingFraction === 'number' ? b.remainingFraction : 0;
        const pct = Math.max(0, Math.min(100, Math.round(frac * 100)));
        groupItems.push({
          group: gLabel,
          isClaude: /claude|gpt/i.test(g.displayName || ''),
          isFiveHour: /5|five/i.test(`${b.displayName || ''} ${b.window || ''} ${b.bucketId || ''}`),
          label: `${gLabel} · ${formatBucketName(b)}`,
          shortLabel: formatBucketName(b),
          pct,
          resetTime: b.resetTime || '',
        });
      }
      groupItems.sort((a, b) => (a.isFiveHour === b.isFiveHour ? 0 : a.isFiveHour ? -1 : 1));
      items.push(...groupItems);
    }
    return items;
  }

  function matchCurrentModel(modelBtnText) {
    if (!cachedModels.length) return null;
    const isClaudeSelected = /claude|gpt|sonnet|opus|haiku/i.test(modelBtnText || '');
    const pool = cachedModels.filter(m => m.isClaude === isClaudeSelected);
    const candidates = pool.length ? pool : cachedModels;
    return candidates.find(m => m.isFiveHour) || candidates[0];
  }

  function updateAllPills() {
    const pills = document.querySelectorAll('.agy-quota-pill');
    pills.forEach((pill) => {
      const anchor = pill._agyAnchorBtn;
      const matched = matchCurrentModel(anchor ? anchor.textContent : '');
      const pct = matched ? matched.pct : null;
      pill.setAttribute('data-level', getLevel(pct));
      const labelEl = pill.querySelector('.agy-quota-pill-text');
      if (labelEl) {
        labelEl.textContent = pct !== null ? `${pct}%` : (isLoading ? '...' : '--%');
      }
      pill.title = matched
        ? `${matched.label}: 剩余 ${matched.pct}% (${formatResetTime(matched.resetTime, matched.pct)})`
        : (lastError ? `配额获取失败: ${lastError}` : '点击查看模型配额');
    });
  }

  function renderPopoverContent() {
    if (!popoverEl) return;
    const refreshBtn = popoverEl.querySelector('.agy-quota-refresh');
    if (refreshBtn) refreshBtn.classList.toggle('spinning', isLoading);
    const listEl = popoverEl.querySelector('.agy-quota-list');
    if (!listEl) return;
    listEl.innerHTML = '';

    if (!cachedModels.length) {
      const empty = document.createElement('div');
      empty.className = 'agy-quota-empty';
      empty.textContent = isLoading
        ? '正在获取模型配额...'
        : (lastError ? `暂无可用配额数据 (${lastError})` : '暂无可用配额数据');
      listEl.appendChild(empty);
      return;
    }

    let lastGroup = '';
    for (const m of cachedModels) {
      if (m.group && m.group !== lastGroup) {
        lastGroup = m.group;
        const gTitle = document.createElement('div');
        gTitle.className = 'agy-quota-group-title';
        gTitle.textContent = m.group;
        listEl.appendChild(gTitle);
      }
      const row = document.createElement('div');
      row.className = 'agy-quota-row';

      const top = document.createElement('div');
      top.className = 'agy-quota-row-top';

      const nameEl = document.createElement('span');
      nameEl.className = 'agy-quota-model-name';
      nameEl.textContent = m.shortLabel || m.label;

      const metaEl = document.createElement('span');
      metaEl.className = 'agy-quota-model-meta';
      metaEl.textContent = `${m.pct}% · ${formatResetTime(m.resetTime, m.pct)}`;

      top.appendChild(nameEl);
      top.appendChild(metaEl);

      const track = document.createElement('div');
      track.className = 'agy-quota-bar-track';

      const fill = document.createElement('div');
      fill.className = 'agy-quota-bar-fill';
      fill.style.width = `${m.pct}%`;
      fill.style.backgroundColor = getBarColor(m.pct);

      track.appendChild(fill);
      row.appendChild(top);
      row.appendChild(track);
      listEl.appendChild(row);
    }
  }

  function closePopover() {
    if (popoverEl && popoverEl.parentNode) popoverEl.parentNode.removeChild(popoverEl);
    popoverEl = null;
    activeAnchorBtn = null;
  }

  function positionPopover(pillEl) {
    if (!popoverEl || !pillEl) return;
    const rect = pillEl.getBoundingClientRect();
    const left = Math.max(12, Math.min(window.innerWidth - 352, rect.left - 40));
    popoverEl.style.left = `${left}px`;
    popoverEl.style.bottom = `${Math.max(16, window.innerHeight - rect.top + 10)}px`;
  }

  function openPopover(pillEl) {
    ensureStyles();
    if (popoverEl && activeAnchorBtn === pillEl) {
      closePopover();
      return;
    }
    closePopover();
    activeAnchorBtn = pillEl;

    const card = document.createElement('div');
    card.className = 'agy-quota-popover';
    card.innerHTML = `
      <div class="agy-quota-header">
        <span class="agy-quota-title">模型配额</span>
        <button type="button" class="agy-quota-refresh" title="刷新配额">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
            <path d="M3 3v5h5"/>
            <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>
            <path d="M16 16h5v5"/>
          </svg>
        </button>
      </div>
      <div class="agy-quota-list"></div>
    `;
    card.addEventListener('click', (e) => e.stopPropagation());
    const refreshBtn = card.querySelector('.agy-quota-refresh');
    if (refreshBtn) refreshBtn.addEventListener('click', () => fetchQuota(true));

    document.body.appendChild(card);
    popoverEl = card;
    positionPopover(pillEl);
    renderPopoverContent();
    fetchQuota(false);
  }

  async function fetchQuota(force) {
    if (isLoading && !force) return;
    isLoading = true;
    updateAllPills();
    renderPopoverContent();
    try {
      const res = await ipc.invoke('quota:get-status');
      if (res && res.ok && res.data) {
        cachedModels = parseModels(res.data);
        lastError = '';
      } else {
        lastError = (res && res.error) ? res.error : '请求失败';
      }
    } catch (err) {
      lastError = String(err);
    } finally {
      isLoading = false;
      updateAllPills();
      renderPopoverContent();
    }
  }

  function isChatInputModelButton(btn) {
    if (!btn || btn.classList.contains('agy-quota-pill')) return false;
    if (btn.closest('.agy-quota-popover')) return false;
    const text = (btn.textContent || '').replace(/\s+/g, ' ').trim();
    if (!text || text.length > 60) return false;
    if (!/(gemini|claude|gpt|hydrogen|helium|lithium|carbon|argon|neon|flash|pro|sonnet|opus|haiku)/i.test(text)) return false;
    let cur = btn.parentElement;
    for (let i = 0; i < 14 && cur && cur !== document.body; i++) {
      if (cur.querySelector('[contenteditable], textarea')) {
        const r = cur.getBoundingClientRect();
        if (r && r.height > 40 && r.height < 420) return true;
      }
      cur = cur.parentElement;
    }
    return false;
  }

  function findHorizontalSlot(btn) {
    let slot = btn;
    for (let i = 0; i < 4 && slot.parentElement && slot.parentElement !== document.body; i++) {
      const cs = window.getComputedStyle(slot.parentElement);
      if (cs.display.includes('flex') && cs.flexDirection !== 'column') return slot;
      slot = slot.parentElement;
    }
    return btn;
  }

  function attachPills() {
    ensureStyles();
    const buttons = document.querySelectorAll('button, [role="button"]');
    for (const btn of buttons) {
      if (!isChatInputModelButton(btn)) continue;
      const slot = findHorizontalSlot(btn);
      if (slot.nextElementSibling && slot.nextElementSibling.classList.contains('agy-quota-pill')) continue;
      const pill = document.createElement('button');
      pill.type = 'button';
      pill.className = 'agy-quota-pill';
      pill.setAttribute('data-level', 'idle');
      pill._agyAnchorBtn = btn;
      pill.innerHTML = `
        <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M13 2L4.5 13.5H11L10 22L19.5 10.5H13L13 2Z"/>
        </svg>
        <span class="agy-quota-pill-text">--%</span>
      `;
      pill.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        openPopover(pill);
      });
      slot.insertAdjacentElement('afterend', pill);
    }
    updateAllPills();
  }

  let attachTimer = null;
  function scheduleAttach() {
    if (attachTimer) return;
    attachTimer = setTimeout(() => {
      attachTimer = null;
      attachPills();
    }, 250);
  }

  function init() {
    attachPills();
    fetchQuota(false);
    setInterval(() => fetchQuota(false), 60000);
    setInterval(attachPills, 2000);
    const observer = new MutationObserver(scheduleAttach);
    const root = document.documentElement || document.body;
    if (root) observer.observe(root, { childList: true, subtree: true });
    document.addEventListener('click', (e) => {
      if (popoverEl && !popoverEl.contains(e.target) && (!activeAnchorBtn || !activeAnchorBtn.contains(e.target))) {
        closePopover();
      }
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && popoverEl) closePopover();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
"""


def default_asar_path():
    if sys.platform == "darwin":
        return "/Applications/Antigravity.app/Contents/Resources/app.asar"
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    return os.path.join(local_app_data, "Programs", "antigravity", "resources", "app.asar")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def unpack_asar(asar_path):
    with open(asar_path, "rb") as f:
        _, header_size, _, json_len = struct.unpack("<4I", f.read(16))
        hdr = json.loads(f.read(json_len).decode("utf-8"))
        base_offset = 8 + header_size
        files_data = {}

        def walk(node, prefix=""):
            for name, meta in node.get("files", {}).items():
                rel = f"{prefix}/{name}" if prefix else name
                if "files" in meta:
                    walk(meta, rel)
                elif not meta.get("unpacked", False):
                    f.seek(base_offset + int(meta["offset"]))
                    files_data[rel] = f.read(meta["size"])

        walk(hdr)
    return hdr, files_data


def pack_asar(hdr, files_data, out_path):
    payloads = []
    cur_offset = 0

    def walk_update(node, prefix=""):
        nonlocal cur_offset
        for name, meta in node.get("files", {}).items():
            rel = f"{prefix}/{name}" if prefix else name
            if "files" in meta:
                walk_update(meta, rel)
            elif not meta.get("unpacked", False):
                data = files_data[rel]
                meta["offset"] = str(cur_offset)
                meta["size"] = len(data)
                payloads.append(data)
                cur_offset += len(data)

    walk_update(hdr)
    json_bytes = json.dumps(hdr, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    json_len = len(json_bytes)
    pad = (4 - (json_len % 4)) % 4
    aligned_len = json_len + pad
    header_bin = struct.pack("<4I", 4, aligned_len + 8, aligned_len + 4, json_len)

    with open(out_path, "wb") as f:
        f.write(header_bin)
        f.write(json_bytes)
        if pad:
            f.write(b"\x00" * pad)
        for chunk in payloads:
            f.write(chunk)


def verify_js_if_node_available(files_map):
    if not shutil.which("node"):
        return
    with tempfile.TemporaryDirectory() as tmpdir:
        for fname, content in files_map.items():
            fpath = os.path.join(tmpdir, fname)
            with open(fpath, "w", encoding="utf-8") as tf:
                tf.write(content)
            res = subprocess.run(["node", "--check", fpath], capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"Syntax check failed for {fname}:\n{res.stderr}")


def main():
    parser = argparse.ArgumentParser(description="Patch Antigravity app.asar with an inline chat quota viewer.")
    parser.add_argument("--asar", default=default_asar_path(), help="Path to Antigravity resources/app.asar")
    parser.add_argument("--output", default=None, help="Write patched app.asar to a separate file instead of overwriting in place")
    parser.add_argument("--restore", action="store_true", help="Restore app.asar from app.asar.bak")
    args = parser.parse_args()

    asar_path = os.path.abspath(args.asar)
    bak_path = asar_path + ".bak"

    if args.restore:
        if not os.path.exists(bak_path):
            raise FileNotFoundError(f"Backup not found: {bak_path}")
        shutil.copy2(bak_path, asar_path)
        print(f"Restored {asar_path} from {bak_path}")
        return

    if not os.path.exists(asar_path):
        raise FileNotFoundError(f"app.asar not found: {asar_path}")

    hdr, files_data = unpack_asar(asar_path)

    ipc_js = files_data["dist/ipcHandlers.js"].decode("utf-8")
    if "quota:get-status" not in ipc_js:
        marker = "    // Per-guest renderer working-set memory in bytes"
        if marker not in ipc_js:
            raise RuntimeError("Anchor marker not found in dist/ipcHandlers.js")
        ipc_js = ipc_js.replace(marker, IPC_ADDITION + "\n" + marker, 1)

    preload_js = files_data["dist/preload.js"].decode("utf-8")
    if "__agyQuotaViewerInitialized" not in preload_js:
        preload_js = preload_js + "\r\n" + PRELOAD_QUOTA_WIDGET

    verify_js_if_node_available({"ipcHandlers.js": ipc_js, "preload.js": preload_js})

    files_data["dist/ipcHandlers.js"] = ipc_js.encode("utf-8")
    files_data["dist/preload.js"] = preload_js.encode("utf-8")

    if args.output:
        out_path = os.path.abspath(args.output)
        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        pack_asar(hdr, files_data, out_path)
        size = os.path.getsize(out_path)
        digest = sha256_file(out_path)
        print(f"Patched successfully: {out_path} (Size={size}, SHA256={digest})")
        return

    if not os.path.exists(bak_path):
        shutil.copy2(asar_path, bak_path)
        print(f"Created backup: {bak_path}")

    tmp_out = asar_path + ".tmp"
    pack_asar(hdr, files_data, tmp_out)
    os.replace(tmp_out, asar_path)
    size = os.path.getsize(asar_path)
    digest = sha256_file(asar_path)
    print(f"Patched successfully: {asar_path} (Size={size}, SHA256={digest})")


if __name__ == "__main__":
    main()
