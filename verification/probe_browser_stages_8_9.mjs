/**
 * DeepVision 4.0 — Real Chrome CDP Probe for Pipeline Stages 8 & 9
 * Stage 8: Browser arrival (Chromium network stack multipart JPEG arrival latency & FPS)
 * Stage 9: Actual display (requestAnimationFrame distinct visual frame paint interval, FPS,
 *          natural 1280x720 resolution, rendered 16:9 aspect ratio, and canvas overlay alignment)
 */
import { spawn } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE_URL = process.env.DEEPVISION_URL || 'http://127.0.0.1:8000';
const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const CDP_PORT = 9344;

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function getJson(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let body = '';
      res.on('data', (c) => (body += c));
      res.on('end', () => {
        try {
          resolve(JSON.parse(body));
        } catch (e) {
          reject(e);
        }
      });
    }).on('error', reject);
  });
}

class CdpSession {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.nextId = 1;
    this.pending = new Map();
  }
  async connect() {
    this.ws = new WebSocket(this.wsUrl);
    await new Promise((resolve, reject) => {
      this.ws.addEventListener('open', resolve, { once: true });
      this.ws.addEventListener('error', reject, { once: true });
    });
    this.ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(typeof ev.data === 'string' ? ev.data : ev.data.toString());
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(msg.error.message));
        else resolve(msg.result);
      }
    });
  }
  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  close() {
    try {
      this.ws?.close();
    } catch {}
  }
}

async function main() {
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dv_stage89_'));
  const chrome = spawn(
    CHROME_PATH,
    [
      `--remote-debugging-port=${CDP_PORT}`,
      `--user-data-dir=${userDataDir}`,
      '--headless=new',
      '--window-size=1440,900',
      '--disable-gpu',
      '--no-first-run',
      '--no-default-browser-check',
      `${BASE_URL}/login/`,
    ],
    { stdio: 'ignore' }
  );

  let cdp = null;
  try {
    let targets = null;
    for (let i = 0; i < 40; i++) {
      try {
        targets = await getJson(`http://127.0.0.1:${CDP_PORT}/json/list`);
        if (Array.isArray(targets) && targets.some((t) => t.type === 'page')) break;
      } catch {}
      await sleep(200);
    }
    const pageTarget = targets.find((t) => t.type === 'page');
    if (!pageTarget) throw new Error('Chrome page target unavailable');

    cdp = new CdpSession(pageTarget.webSocketDebuggerUrl);
    await cdp.connect();
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Emulation.setDeviceMetricsOverride', {
      width: 1440,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });

    await sleep(1200);

    // Establish authenticated Demo Operator session with valid CSRF token
    const authRes = await cdp.send('Runtime.evaluate', {
      awaitPromise: true,
      returnByValue: true,
      expression: `(async () => {
        const c = await fetch('/api/auth/csrf/', { credentials: 'include' }).then(r => r.json());
        const d = await fetch('/api/auth/demo-session/', {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': c.csrfToken },
          body: '{}'
        });
        return { status: d.status };
      })()`,
    });
    if (authRes?.result?.value?.status !== 200) {
      throw new Error(`Demo session auth failed: ${JSON.stringify(authRes?.result?.value)}`);
    }

    // Navigate directly to Live View for Camera 4 (Webcam 0)
    await cdp.send('Page.navigate', { url: `${BASE_URL}/cameras/4/preview/` });
    await sleep(3500);

    // Measure Stage 8 (Browser multipart arrival) and Stage 9 (Actual rAF display + DOM geometry)
    const probeRes = await cdp.send('Runtime.evaluate', {
      awaitPromise: true,
      returnByValue: true,
      expression: `(async () => {
        // Wait up to 6s for img naturalWidth > 0
        let img = null;
        for (let i = 0; i < 30; i++) {
          img = document.querySelector('img[src*="/stream"]') || document.querySelector('.dv-stream-img') || document.querySelector('img');
          if (img && img.complete && img.naturalWidth > 0) break;
          await new Promise(r => setTimeout(r, 200));
        }
        const canvas = document.querySelector('canvas');

        // Stage 8: Measure Chromium multipart arrival times via ReadableStream for 4.0 seconds
        const arrivalAssemblyMs = [];
        const arrivalIntervalsMs = [];
        const ctrl = new AbortController();
        const streamTask = (async () => {
          const resp = await fetch('/api/cameras/4/stream/?mode=tracking&_probe=' + Date.now(), {
            credentials: 'include',
            signal: ctrl.signal,
          });
          const reader = resp.body.getReader();
          let buf = new Uint8Array(0);
          let frameStartTs = null;
          let lastFrameArrivalTs = null;
          const tEnd = performance.now() + 4200;

          const concat = (a, b) => {
            const out = new Uint8Array(a.length + b.length);
            out.set(a, 0);
            out.set(b, a.length);
            return out;
          };

          while (performance.now() < tEnd) {
            const { done, value } = await reader.read();
            const now = performance.now();
            if (done || !value) break;
            if (frameStartTs === null) frameStartTs = now;
            buf = concat(buf, value);

            // Scan for JPEG SOI (0xFF 0xD8) and EOI (0xFF 0xD9)
            let searchFrom = 0;
            while (searchFrom < buf.length - 1) {
              let soi = -1;
              for (let i = searchFrom; i < buf.length - 1; i++) {
                if (buf[i] === 0xff && buf[i + 1] === 0xd8) { soi = i; break; }
              }
              if (soi < 0) break;
              let eoi = -1;
              for (let j = soi + 2; j < buf.length - 1; j++) {
                if (buf[j] === 0xff && buf[j + 1] === 0xd9) { eoi = j + 2; break; }
              }
              if (eoi < 0) break;

              const assembly = Math.max(0.05, now - frameStartTs);
              arrivalAssemblyMs.push(assembly);
              if (lastFrameArrivalTs !== null) {
                arrivalIntervalsMs.push(now - lastFrameArrivalTs);
              }
              lastFrameArrivalTs = now;
              buf = buf.slice(eoi);
              frameStartTs = buf.length > 0 ? now : null;
              searchFrom = 0;
            }
          }
          try { ctrl.abort(); } catch {}
        })().catch(() => {});

        // Stage 9: Measure actual visual display updates via requestAnimationFrame pixel sampling on the rendered <img>
        const displayPaintLatencyMs = [];
        const displayIntervalsMs = [];
        const off = document.createElement('canvas');
        off.width = 64;
        off.height = 36;
        const ctx = off.getContext('2d', { willReadFrequently: true });
        let prevPixels = null;
        let lastVisualChangeTs = null;

        const rafTask = new Promise((resolve) => {
          const start = performance.now();
          function tick(ts) {
            if (img && img.naturalWidth > 0) {
              const t0 = performance.now();
              try {
                ctx.drawImage(img, 0, 0, 64, 36);
                const data = ctx.getImageData(0, 0, 64, 36).data;
                const t1 = performance.now();
                if (prevPixels) {
                  let diff = 0;
                  for (let k = 0; k < data.length; k += 16) {
                    diff += Math.abs(data[k] - prevPixels[k]);
                  }
                  if (diff > 40) {
                    displayPaintLatencyMs.push(Math.max(0.05, t1 - t0) + (lastVisualChangeTs ? 0 : 0));
                    if (lastVisualChangeTs !== null) {
                      displayIntervalsMs.push(ts - lastVisualChangeTs);
                    }
                    lastVisualChangeTs = ts;
                    prevPixels = new Uint8Array(data);
                  }
                } else {
                  prevPixels = new Uint8Array(data);
                  lastVisualChangeTs = ts;
                }
              } catch {}
            }
            if (ts - start < 4200) {
              requestAnimationFrame(tick);
            } else {
              resolve();
            }
          }
          requestAnimationFrame(tick);
        });

        await Promise.all([streamTask, rafTask]);

        // Toggle interactive perimeter SVG overlay (#camera-zone-overlay) to verify pixel-exact DOM alignment with #camera-live-stream
        const zoneBtn = document.querySelector('#btn-toggle-zone-editor');
        if (zoneBtn && !document.querySelector('#camera-zone-overlay')) {
          zoneBtn.click();
          await new Promise(r => setTimeout(r, 150));
        }
        const overlayEl = document.querySelector('#camera-zone-overlay') || document.querySelector('canvas');
        const imgRect = img ? img.getBoundingClientRect() : null;
        const overlayRect = overlayEl ? overlayEl.getBoundingClientRect() : null;

        return {
          natural_width: img ? img.naturalWidth : 0,
          natural_height: img ? img.naturalHeight : 0,
          rendered_width: imgRect ? Number(imgRect.width.toFixed(2)) : 0,
          rendered_height: imgRect ? Number(imgRect.height.toFixed(2)) : 0,
          rendered_aspect_ratio: (imgRect && imgRect.height > 0) ? Number((imgRect.width / imgRect.height).toFixed(4)) : 0,
          overlay_canvas_present: Boolean(overlayEl),
          overlay_alignment_delta_px: (imgRect && overlayRect && overlayRect.width > 0)
            ? Number(Math.max(
                Math.abs(imgRect.left - overlayRect.left),
                Math.abs(imgRect.top - overlayRect.top),
                Math.abs(imgRect.width - overlayRect.width),
                Math.abs(imgRect.height - overlayRect.height)
              ).toFixed(2))
            : 0,
          stage8_arrival_assembly_ms: arrivalAssemblyMs,
          stage8_arrival_intervals_ms: arrivalIntervalsMs,
          stage9_display_intervals_ms: displayIntervalsMs,
          stage9_distinct_frames_displayed: displayIntervalsMs.length + 1,
        };
      })()`,
    });

    process.stdout.write(JSON.stringify(probeRes?.result?.value || {}));
  } finally {
    cdp?.close();
    try {
      chrome.kill();
    } catch {}
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
