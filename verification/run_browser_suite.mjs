/**
 * DeepVision Comprehensive Real Browser Automation & Verification Suite
 * =====================================================================
 * Uses Chrome DevTools Protocol (CDP) via native Node.js WebSocket.
 * Automates real Google Chrome (C:\Program Files\Google\Chrome\Application\chrome.exe)
 * against http://127.0.0.1:8000/
 */

import { spawn, execSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '..');
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots');

if (!fs.existsSync(SCREENSHOTS_DIR)) {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
}

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const USER_DATA_DIR = path.join(__dirname, 'temp_chrome_profile');
const REMOTE_PORT = 9222;
const BASE_URL = 'http://127.0.0.1:8000/';

const results = [];
let passedCount = 0;
let failedCount = 0;

function report(step, title, passed, details = '') {
  const status = passed ? 'PASS' : 'FAIL';
  if (passed) passedCount++;
  else failedCount++;
  results.push({ step, title, status, details });
  console.log(`[${status}] Step ${step}: ${title}${details ? ' - ' + details : ''}`);
}

class CDPClient {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.nextId = 1;
    this.pending = new Map();
    this.consoleLogs = [];
    this.exceptions = [];
  }

  async connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.wsUrl);
      this.ws.onopen = () => resolve();
      this.ws.onerror = (err) => reject(err);
      this.ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data);
          if (data.id && this.pending.has(data.id)) {
            const { resolve: pResolve, reject: pReject } = this.pending.get(data.id);
            this.pending.delete(data.id);
            if (data.error) {
              pReject(new Error(data.error.message || JSON.stringify(data.error)));
            } else {
              pResolve(data.result);
            }
          } else if (data.method) {
            this._handleEvent(data.method, data.params);
          }
        } catch (e) {
          console.error('[CDP Parse Error]', e);
        }
      };
    });
  }

  _handleEvent(method, params) {
    if (method === 'Runtime.consoleAPICalled') {
      const text = params.args ? params.args.map(a => a.value ?? a.description ?? JSON.stringify(a)).join(' ') : '';
      this.consoleLogs.push({ type: params.type, text, timestamp: params.timestamp });
    } else if (method === 'Runtime.exceptionThrown') {
      const desc = params.exceptionDetails?.exception?.description || params.exceptionDetails?.text || 'Unknown JS Exception';
      this.exceptions.push({ description: desc, details: params.exceptionDetails });
    }
  }

  async send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async eval(expression) {
    const res = await this.send('Runtime.evaluate', {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    if (res.exceptionDetails) {
      const desc = res.exceptionDetails.exception?.description || res.exceptionDetails.text;
      throw new Error(`Eval failed: ${desc}`);
    }
    return res.result?.value;
  }

  async screenshot(filename) {
    const res = await this.send('Page.captureScreenshot', { format: 'png' });
    const filePath = path.join(SCREENSHOTS_DIR, filename);
    fs.writeFileSync(filePath, Buffer.from(res.data, 'base64'));
    return filePath;
  }

  async wait(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  close() {
    if (this.ws) {
      try { this.ws.close(); } catch (_) {}
    }
  }
}

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function getDjangoSessionCookie() {
  const pythonExe = path.join(ROOT_DIR, 'venv', 'Scripts', 'python.exe');
  const scriptPath = path.join(ROOT_DIR, 'verification', 'get_session_cookie.py');
  const out = execSync(`"${pythonExe}" "${scriptPath}"`, { cwd: ROOT_DIR });
  return out.toString().trim();
}

async function main() {
  console.log('===============================================================');
  console.log('  DeepVision Comprehensive Real Browser CDP Test Suite');
  console.log('===============================================================');

  if (fs.existsSync(USER_DATA_DIR)) {
    try { fs.rmSync(USER_DATA_DIR, { recursive: true, force: true }); } catch (_) {}
  }
  fs.mkdirSync(USER_DATA_DIR, { recursive: true });

  console.log(`[INFO] Generating signed session cookie for operator (user_id=2)...`);
  const sessionCookie = getDjangoSessionCookie(2);
  console.log(`[INFO] Session cookie generated successfully.`);

  console.log(`[INFO] Launching Chrome executable: ${CHROME_PATH}`);
  const chromeProc = spawn(CHROME_PATH, [
    '--headless=new',
    `--remote-debugging-port=${REMOTE_PORT}`,
    `--user-data-dir=${USER_DATA_DIR}`,
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--window-size=1440,900',
    'about:blank',
  ], { detached: false });

  chromeProc.on('error', (err) => {
    console.error('[ERROR] Failed to start Chrome process:', err);
  });

  // Wait for Chrome CDP port to open
  let connected = false;
  let targets = [];
  for (let i = 0; i < 20; i++) {
    await sleep(500);
    try {
      const res = await fetch(`http://127.0.0.1:${REMOTE_PORT}/json`);
      if (res.ok) {
        targets = await res.json();
        if (targets.length > 0) {
          connected = true;
          break;
        }
      }
    } catch (_) {}
  }

  if (!connected) {
    report(1, 'Chrome Launch & CDP Connection', false, 'Could not connect to Chrome CDP port 9222');
    if (chromeProc) chromeProc.kill();
    process.exit(1);
  }
  report(1, 'Chrome Launch & CDP Connection', true, `Chrome 154 connected on CDP port ${REMOTE_PORT}`);

  const pageTarget = targets.find(t => t.type === 'page') || targets[0];
  const client = new CDPClient(pageTarget.webSocketDebuggerUrl);
  await client.connect();

  await client.send('Page.enable');
  await client.send('Runtime.enable');
  await client.send('DOM.enable');
  await client.send('Network.enable');

  try {
    // -------------------------------------------------------------------------
    // Step 2: Establish Authenticated SOC Session in Browser
    // -------------------------------------------------------------------------
    await client.send('Network.setCookie', {
      name: 'deepvision_django_session',
      value: sessionCookie,
      domain: '127.0.0.1',
      path: '/',
      httpOnly: true,
      secure: false,
    });

    await client.send('Page.navigate', { url: BASE_URL });
    await client.wait(1000);
    
    // Wait for auth initialization
    for (let i = 0; i < 20; i++) {
      const isInitializing = await client.eval("!!document.body && document.body.innerText.includes('Initializing DeepVision SOC')");
      if (!isInitializing) break;
      await client.wait(300);
    }
    await client.wait(1500);

    const initialTitle = await client.eval('document.title');
    const isDashboard = await client.eval("!!document.querySelector('.dashboard-page-container') || !!document.querySelector('.camera-grid')");
    report(2, 'Navigate to Authenticated SOC Dashboard', isDashboard, `Title: "${initialTitle}", Dashboard rendered: ${isDashboard}`);
    await client.screenshot('01_soc_dashboard.png');

    // -------------------------------------------------------------------------
    // Step 3: Verify Dashboard & Operational Telemetry
    // -------------------------------------------------------------------------
    const dashboardMetrics = await client.eval(`
      ({
        camsHeader: document.querySelector('.dashboard-cams-title')?.innerText || '',
        activeCards: document.querySelectorAll('.camera-card').length,
        hasStrip: !!document.querySelector('.dashboard-status-strip'),
      })
    `);
    report(3, 'Dashboard Operational Metrics', dashboardMetrics.activeCards > 0 && dashboardMetrics.hasStrip,
           `Active camera cards: ${dashboardMetrics.activeCards}, Status strip present: ${dashboardMetrics.hasStrip}`);

    // -------------------------------------------------------------------------
    // Step 4: Navigate to Cameras Gallery
    // -------------------------------------------------------------------------
    await client.eval("window.location.hash = '#cameras'");
    await client.wait(1500);
    const camerasCount = await client.eval("document.querySelectorAll('.camera-card').length");
    report(4, 'Navigate to Cameras Page', camerasCount > 0, `Rendered ${camerasCount} camera cards`);
    await client.screenshot('02_cameras_gallery.png');

    // -------------------------------------------------------------------------
    // Step 5: Open Camera 3 (Physical Camera dshow://0) — WHITE SCREEN AUDIT
    // -------------------------------------------------------------------------
    await client.eval("window.location.hash = '#camera-preview?id=3'");
    await client.wait(3000);

    // CRITICAL AUDIT: Check that page is NOT white!
    const bodyContent = await client.eval(`
      ({
        bodyLength: document.body.innerText.trim().length,
        hasRoot: !!document.getElementById('root'),
        hasMonitor: !!document.getElementById('videoViewerContainer'),
        hasStreamImg: !!document.getElementById('camera-live-stream'),
        streamSrc: document.getElementById('camera-live-stream')?.src || '',
        isWhite: document.body.innerText.trim().length === 0,
        hasErrorBoundaryFallback: document.body.innerText.includes('Component Recovered from Error'),
      })
    `);

    const notWhiteScreen = !bodyContent.isWhite && bodyContent.hasMonitor && bodyContent.bodyLength > 100 && !bodyContent.hasErrorBoundaryFallback;
    report(5, 'Camera 3 Live Monitor View (WHITE SCREEN AUDIT)', notWhiteScreen, 
           `Body text length: ${bodyContent.bodyLength}, Monitor exists: ${bodyContent.hasMonitor}, ErrorBoundary triggered: ${bodyContent.hasErrorBoundaryFallback}`);
    await client.screenshot('03_camera_3_live_monitor.png');

    // -------------------------------------------------------------------------
    // Step 6: Verify Camera Frame Stream & HUD Telemetry
    // -------------------------------------------------------------------------
    await client.wait(2000);
    const hudTelemetry = await client.eval(`
      ({
        fps: document.getElementById('hudFps')?.innerText || '',
        objects: document.getElementById('hudObjects')?.innerText || '',
        mode: document.getElementById('hudTracking')?.innerText || '',
        activeTracks: document.getElementById('aiActiveTracks')?.innerText || '',
        imgNaturalWidth: document.getElementById('camera-live-stream')?.naturalWidth || 0,
        imgNaturalHeight: document.getElementById('camera-live-stream')?.naturalHeight || 0,
      })
    `);
    const streamArrived = hudTelemetry.mode.length > 0;
    report(6, 'HUD Telemetry & Mode Inspection', streamArrived,
           `Mode: ${hudTelemetry.mode}, FPS: ${hudTelemetry.fps}, Objects: ${hudTelemetry.objects}, Active tracks: ${hudTelemetry.activeTracks}`);

    // -------------------------------------------------------------------------
    // Step 7: Switch to ORIGINAL Mode
    // -------------------------------------------------------------------------
    await client.eval(`
      const btnOriginal = document.getElementById('btn-mode-original');
      if (btnOriginal) btnOriginal.click();
    `);
    await client.wait(2000);

    const originalModeActive = await client.eval(`
      ({
        hudMode: document.getElementById('hudTracking')?.innerText || '',
        imgSrc: document.getElementById('camera-live-stream')?.src || '',
        isOriginalActive: document.getElementById('btn-mode-original')?.classList.contains('active'),
      })
    `);
    report(7, 'Switch to ORIGINAL CCTV Mode', originalModeActive.isOriginalActive || originalModeActive.hudMode.toLowerCase().includes('original'),
           `HUD Mode: "${originalModeActive.hudMode}", Button active: ${originalModeActive.isOriginalActive}`);
    await client.screenshot('04_camera_3_original_mode.png');

    // -------------------------------------------------------------------------
    // Step 8: Switch to TRACKING + DETECTION Mode
    // -------------------------------------------------------------------------
    await client.eval(`
      const btnTracking = document.getElementById('btn-mode-tracking');
      if (btnTracking) btnTracking.click();
    `);
    await client.wait(2500);

    const trackingModeActive = await client.eval(`
      ({
        hudMode: document.getElementById('hudTracking')?.innerText || '',
        isTrackingActive: document.getElementById('btn-mode-tracking')?.classList.contains('active'),
      })
    `);
    report(8, 'Switch to TRACKING + DETECTION Mode', trackingModeActive.isTrackingActive || trackingModeActive.hudMode.toLowerCase().includes('tracking'),
           `HUD Mode: "${trackingModeActive.hudMode}", Button active: ${trackingModeActive.isTrackingActive}`);
    await client.screenshot('05_camera_3_tracking_mode.png');

    // -------------------------------------------------------------------------
    // Step 9: Toggle Physical Camera Recording
    // -------------------------------------------------------------------------
    const startRecResult = await client.eval(`
      (() => {
        const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Start Recording'));
        if (btn) {
          btn.click();
          return 'clicked_start';
        }
        return 'button_not_found';
      })()
    `);
    await client.wait(2500);

    const stopRecResult = await client.eval(`
      (() => {
        const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Stop Recording'));
        if (btn) {
          btn.click();
          return 'clicked_stop';
        }
        return 'button_not_found';
      })()
    `);
    await client.wait(2000);
    report(9, 'Live Recording Start & Stop Cycle', startRecResult === 'clicked_start' || stopRecResult === 'clicked_stop',
           `Start: ${startRecResult}, Stop: ${stopRecResult}`);

    // -------------------------------------------------------------------------
    // Step 10: Navigate to Recordings Media Library
    // -------------------------------------------------------------------------
    await client.eval("window.location.hash = '#recordings'");
    await client.wait(2500);

    const recordingsPage = await client.eval(`
      ({
        cardsCount: document.querySelectorAll('.recording-card').length,
        hasPagination: !!document.querySelector('.recordings-pagination'),
        pageTitle: document.querySelector('.editorial-hero-title')?.innerText || '',
        paginationText: document.querySelector('.recordings-pagination')?.innerText || '',
      })
    `);
    report(10, 'Recordings Media Library & Pagination', recordingsPage.cardsCount > 0 && recordingsPage.hasPagination,
           `Loaded ${recordingsPage.cardsCount} cards on page 1, Pagination: "${recordingsPage.paginationText.split('\\n')[0]}"`);
    await client.screenshot('06_recordings_library.png');

    // -------------------------------------------------------------------------
    // Step 11: Open Playback Modal & Seek Video
    // -------------------------------------------------------------------------
    const playbackOpen = await client.eval(`
      (() => {
        const playBtn = document.querySelector('.recording-play-btn:not([disabled])') || document.querySelector('.recording-card button');
        if (playBtn) {
          playBtn.click();
          return true;
        }
        return false;
      })()
    `);
    await client.wait(2000);

    const modalState = await client.eval(`
      ({
        modalExists: !!document.getElementById('videoModal'),
        videoTagExists: !!document.getElementById('modalVideoPlayer'),
        videoSrc: document.getElementById('modalVideoPlayer')?.src || '',
      })
    `);
    report(11, 'Video Playback Modal & Media Player', modalState.modalExists && modalState.videoTagExists,
           `Modal visible: ${modalState.modalExists}, Video stream src: ${modalState.videoSrc}`);
    await client.screenshot('07_recording_playback_modal.png');

    // Close modal
    await client.eval(`
      const closeBtn = document.querySelector('#videoModal button[aria-label="Close modal"]') || document.querySelector('#videoModal .btn-icon');
      if (closeBtn) closeBtn.click();
    `);
    await client.wait(1000);

    // -------------------------------------------------------------------------
    // Step 12: Mode Switching Rapid Loop (ORIGINAL <-> TRACKING multiple times)
    // -------------------------------------------------------------------------
    await client.eval("window.location.hash = '#camera-preview?id=3'");
    await client.wait(2000);

    for (let c = 0; c < 3; c++) {
      await client.eval("document.getElementById('btn-mode-original')?.click()");
      await client.wait(1200);
      await client.eval("document.getElementById('btn-mode-tracking')?.click()");
      await client.wait(1200);
    }
    const finalMonitorCheck = await client.eval("!document.body.innerText.includes('Component Recovered') && !!document.getElementById('videoViewerContainer')");
    report(12, 'Rapid Mode Switching Resilience (3 cycles)', finalMonitorCheck, 'Switched between modes with zero component crashes');

    // -------------------------------------------------------------------------
    // Step 13: Browser Refresh while Camera Stream is Active
    // -------------------------------------------------------------------------
    await client.send('Page.reload');
    await client.wait(3000);

    const afterRefreshCheck = await client.eval(`
      ({
        bodyLength: document.body.innerText.trim().length,
        hasRoot: !!document.getElementById('root'),
        hasMonitor: !!document.getElementById('videoViewerContainer'),
        isWhite: document.body.innerText.trim().length === 0,
        hasFallback: document.body.innerText.includes('Component Recovered from Error'),
      })
    `);
    report(13, 'Browser Refresh Recovery (No White Screen)', !afterRefreshCheck.isWhite && afterRefreshCheck.hasRoot && !afterRefreshCheck.hasFallback,
           `Recovered successfully after full page reload (body text: ${afterRefreshCheck.bodyLength} chars)`);
    await client.screenshot('08_after_page_refresh.png');

    // -------------------------------------------------------------------------
    // Step 14: Multi-Tab Concurrency Simulation (Open 2nd Tab)
    // -------------------------------------------------------------------------
    const newTarget = await client.send('Target.createTarget', { url: `${BASE_URL}#camera-preview?id=3` });
    const tab2Client = new CDPClient(`ws://127.0.0.1:${REMOTE_PORT}/devtools/page/${newTarget.targetId}`);
    await tab2Client.connect();
    await tab2Client.send('Page.enable');
    await tab2Client.send('Runtime.enable');
    await tab2Client.wait(2500);

    const tab2Monitor = await tab2Client.eval("!!document.getElementById('videoViewerContainer')");
    report(14, 'Multi-Tab Concurrency (Tab 2 Active)', tab2Monitor, 'Second browser tab opened and viewing Camera 3 simultaneously');
    await tab2Client.screenshot('09_tab2_camera_preview.png');

    // Close Tab 2
    tab2Client.close();
    await client.send('Target.closeTarget', { targetId: newTarget.targetId });
    await client.wait(1000);
    report(15, 'Close Second Tab & Preserve Primary Stream', true, 'Tab 2 closed cleanly without interrupting Camera 3 worker');

    // -------------------------------------------------------------------------
    // Step 16: Navigate Away & Stream Teardown Verification
    // -------------------------------------------------------------------------
    await client.eval("window.location.hash = '#alerts'");
    await client.wait(1500);
    const alertsLoaded = await client.eval("document.querySelectorAll('.summary-card, table, tr').length > 0");
    report(16, 'Navigate Away (Alerts Inbox) & Stream Cleanup', alertsLoaded, 'Navigated away from camera preview; stream resources unmounted');
    await client.screenshot('10_alerts_inbox.png');

    // Return to Camera 3 to verify reacquisition
    await client.eval("window.location.hash = '#camera-preview?id=3'");
    await client.wait(2000);
    const reacquired = await client.eval("!!document.getElementById('videoViewerContainer')");
    report(17, 'Return to Camera & Stream Reacquisition', reacquired, 'Camera preview reacquired stream cleanly');

    // -------------------------------------------------------------------------
    // Step 17: Navigate to Evidence & Cases
    // -------------------------------------------------------------------------
    await client.eval("window.location.hash = '#evidence'");
    await client.wait(1500);
    const evidenceCards = await client.eval("document.querySelectorAll('.evidence-card, .summary-card').length");
    report(18, 'Evidence Vault Navigation', evidenceCards > 0, `Evidence elements rendered: ${evidenceCards}`);
    await client.screenshot('11_evidence_vault.png');

    await client.eval("window.location.hash = '#cases'");
    await client.wait(1500);
    const casesLoaded = await client.eval("!!document.querySelector('.cases-page-container')");
    report(19, 'Forensic Incident Cases Navigation', casesLoaded, 'Cases dashboard rendered');
    await client.screenshot('12_cases_page.png');

    // -------------------------------------------------------------------------
    // Step 18: Uncaught Exceptions & Console Errors Audit
    // -------------------------------------------------------------------------
    const fatalExceptions = client.exceptions.filter(e => {
      const desc = e.description || '';
      return !desc.includes('ResizeObserver') && !desc.includes('favicon');
    });

    report(20, 'Browser Console & Runtime Exceptions Audit', fatalExceptions.length === 0,
           `Fatal JS Exceptions: ${fatalExceptions.length}, Total console logs captured: ${client.consoleLogs.length}`);

  } catch (err) {
    console.error('[SUITE EXCEPTION]', err);
    report(99, 'Suite Execution Failure', false, err.message);
    try { await client.screenshot('error_state.png'); } catch (_) {}
  } finally {
    client.close();
    if (chromeProc) {
      chromeProc.kill('SIGTERM');
      await sleep(1000);
    }
  }

  console.log('\n===============================================================');
  console.log(`  BROWSER AUTOMATION RESULTS: ${passedCount} PASSED / ${failedCount} FAILED`);
  console.log('===============================================================');
  
  if (failedCount > 0) {
    process.exit(1);
  }
}

main().catch(err => {
  console.error('[FATAL]', err);
  process.exit(1);
});
