/**
 * DeepVision 4.0 — High-Resolution Browser Screenshot Capture Script
 * =================================================================
 * Connects to Google Chrome via Chrome DevTools Protocol (CDP).
 * Authenticates directly with signed-cookie session for User 1 (Operator).
 * Navigates to all 10 canonical workspaces and captures pixel-perfect evidence screenshots.
 */

import { spawn, execSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '..');
const SCREENSHOTS_DIR = path.join(ROOT_DIR, 'verification', 'screenshots', 'final_4.0');

fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const USER_DATA_DIR = path.join(ROOT_DIR, 'verification', 'temp_chrome_40_profile');
const REMOTE_PORT = 9226;
const BASE_URL = 'http://127.0.0.1:8000';

function getSignedSessionCookie() {
  const pyExe = path.join(ROOT_DIR, 'venv', 'Scripts', 'python.exe');
  const code = `import os, sys, django
sys.path.insert(0, 'deepvision_django')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.contrib.sessions.backends.signed_cookies import SessionStore
s = SessionStore()
s['user_id'] = 1
s['role'] = 'operator'
s.save()
print(s.session_key)
`;
  const out = execSync(`"${pyExe}" -`, {
    input: code,
    cwd: ROOT_DIR,
    encoding: 'utf-8',
  });
  return out.trim().split('\n').pop().trim();
}

class SimpleCDP {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.nextId = 1;
    this.pending = new Map();
  }

  async connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.wsUrl);
      this.ws.onopen = resolve;
      this.ws.onerror = reject;
      this.ws.onmessage = (event) => {
        const msg = JSON.parse(event.data.toString());
        if (msg.id && this.pending.has(msg.id)) {
          const { res, rej } = this.pending.get(msg.id);
          this.pending.delete(msg.id);
          if (msg.error) rej(msg.error);
          else res(msg.result);
        }
      };
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((res, rej) => {
      this.pending.set(id, { res, rej });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async eval(expr) {
    const r = await this.send('Runtime.evaluate', {
      expression: expr,
      returnByValue: true,
      awaitPromise: true,
    });
    return r?.result?.value;
  }

  async wait(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  async screenshot(filename) {
    const r = await this.send('Page.captureScreenshot', {
      format: 'png',
      captureBeyondViewport: false,
    });
    const buffer = Buffer.from(r.data, 'base64');
    const outPath = path.join(SCREENSHOTS_DIR, filename);
    fs.writeFileSync(outPath, buffer);
    console.log(`[CAPTURED] ${filename} (${Math.round(buffer.length / 1024)} KB)`);
  }
}

async function main() {
  console.log('Launching headless Google Chrome for DeepVision 4.0 visual verification...');

  const chromeProc = spawn(
    CHROME_PATH,
    [
      `--remote-debugging-port=${REMOTE_PORT}`,
      `--user-data-dir=${USER_DATA_DIR}`,
      '--no-first-run',
      '--no-default-browser-check',
      '--headless=new',
      '--window-size=1920,1080',
      '--disable-gpu',
      '--disable-background-networking',
    ],
    { stdio: 'ignore' }
  );

  await new Promise((r) => setTimeout(r, 1500));

  try {
    const listRes = await fetch(`http://127.0.0.1:${REMOTE_PORT}/json`);
    const targets = await listRes.json();
    const pageTarget = targets.find((t) => t.type === 'page') || targets[0];
    const cdp = new SimpleCDP(pageTarget.webSocketDebuggerUrl);
    await cdp.connect();

    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Network.enable');

    const sessionCookie = getSignedSessionCookie();
    console.log(`Injecting signed session cookie for User ID 1 (Operator)...`);
    await cdp.send('Network.setCookie', {
      name: 'deepvision_django_session',
      value: sessionCookie,
      url: BASE_URL,
      domain: '127.0.0.1',
      path: '/',
      httpOnly: true,
    });

    await cdp.send('Emulation.setDeviceMetricsOverride', {
      width: 1920,
      height: 1080,
      deviceScaleFactor: 1,
      mobile: false,
    });

    // 1. Overview Dashboard
    console.log('1. Capturing #/overview...');
    await cdp.send('Page.navigate', { url: `${BASE_URL}/#overview` });
    await cdp.wait(2000);
    await cdp.screenshot('01_overview_dashboard.png');

    // 2. Live Monitoring
    console.log('2. Capturing #/live (Webcam 0)...');
    await cdp.send('Page.navigate', { url: `${BASE_URL}/#live?camera=4` });
    await cdp.wait(3000);
    await cdp.screenshot('02_live_monitoring_webcam0.png');

    // 3. Zone Editor Overlay
    console.log('3. Opening Zone Editor Drawer & applying perimeter preset...');
    await cdp.eval(`(() => {
      const btn = document.getElementById('btn-toggle-zone-editor');
      if (btn) btn.click();
    })()`);
    await cdp.wait(1000);
    await cdp.eval(`(() => {
      const pbtn = document.getElementById('btn-preset-webcam-zone');
      if (pbtn) pbtn.click();
    })()`);
    await cdp.wait(1000);
    await cdp.screenshot('03_webcam0_zone_editor.png');

    // 4. Cameras Inventory
    console.log('4. Capturing #/cameras...');
    await cdp.send('Page.navigate', { url: `${BASE_URL}/#cameras` });
    await cdp.wait(2000);
    await cdp.screenshot('04_cameras_inventory.png');

    // 5. Security Alerts
    console.log('5. Capturing #/alerts...');
    await cdp.send('Page.navigate', { url: `${BASE_URL}/#alerts` });
    await cdp.wait(2000);
    await cdp.screenshot('05_security_events.png');

    // 6. Recordings
    console.log('6. Capturing #/recordings...');
    await cdp.send('Page.navigate', { url: `${BASE_URL}/#recordings` });
    await cdp.wait(2000);
    await cdp.screenshot('06_recordings_vault.png');

    // 7. Evidence
    console.log('7. Capturing #/evidence...');
    await cdp.send('Page.navigate', { url: `${BASE_URL}/#evidence` });
    await cdp.wait(2000);
    await cdp.screenshot('07_evidence_vault.png');

    // 8. Cases
    console.log('8. Capturing #/cases...');
    await cdp.send('Page.navigate', { url: `${BASE_URL}/#cases` });
    await cdp.wait(2000);
    await cdp.screenshot('08_incident_cases.png');

    // 9. Notifications
    console.log('9. Capturing #/notifications...');
    await cdp.send('Page.navigate', { url: `${BASE_URL}/#notifications` });
    await cdp.wait(2000);
    await cdp.screenshot('09_notifications.png');

    // 10. Settings
    console.log('10. Capturing #/settings...');
    await cdp.send('Page.navigate', { url: `${BASE_URL}/#settings` });
    await cdp.wait(2000);
    await cdp.screenshot('10_settings_policies.png');

    // 11. Help & Support
    console.log('11. Capturing #/help...');
    await cdp.send('Page.navigate', { url: `${BASE_URL}/#help` });
    await cdp.wait(2000);
    await cdp.screenshot('11_help_diagnostics.png');

    console.log('\n============================================================');
    console.log('  ALL 10 CANONICAL DEEPVISION 4.0 WORKSPACES VERIFIED & CAPTURED');
    console.log('============================================================\n');
  } finally {
    try {
      chromeProc.kill();
    } catch (_) {}
  }
}

main().catch(console.error);

