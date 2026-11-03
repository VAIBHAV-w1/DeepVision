/**
 * Captures clean, high-resolution evidence screenshots of DeepVision 3.0:
 * 1. Overview Dashboard
 * 2. Live Surveillance with Zone Editor & Perimeter
 * 3. 10-Item Canonical Navigation
 * 4. Security Alerts
 */
import { spawn, execSync } from "child_process";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, "..");
const SCREENSHOTS_DIR = path.join(
  ROOT_DIR,
  "verification",
  "screenshots",
  "final_3.0",
);

fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

const CHROME_PATH =
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const USER_DATA_DIR = path.join(
  ROOT_DIR,
  "verification",
  "temp_chrome_30_profile",
);
const REMOTE_PORT = 9225;
const BASE_URL = "http://127.0.0.1:8000";

function getSignedSessionCookie() {
  const pyExe = path.join(ROOT_DIR, "venv", "Scripts", "python.exe");
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
    encoding: "utf-8",
  });
  return out.trim().split("\n").pop().trim();
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
    const r = await this.send("Runtime.evaluate", {
      expression: expr,
      returnByValue: true,
      awaitPromise: true,
    });
    return r?.result?.value;
  }

  async screenshot(filename) {
    const r = await this.send("Page.captureScreenshot", {
      format: "png",
      quality: 95,
    });
    const buffer = Buffer.from(r.data, "base64");
    const outPath = path.join(SCREENSHOTS_DIR, filename);
    fs.writeFileSync(outPath, buffer);
    console.log(`[SCREENSHOT] Saved: ${outPath} (${buffer.length} bytes)`);
  }

  async wait(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }
}

async function main() {
  if (fs.existsSync(USER_DATA_DIR)) {
    try {
      fs.rmSync(USER_DATA_DIR, { recursive: true, force: true });
    } catch (_) {}
  }

  const chromeProc = spawn(
    CHROME_PATH,
    [
      `--remote-debugging-port=${REMOTE_PORT}`,
      `--user-data-dir=${USER_DATA_DIR}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--headless=new",
      "--window-size=1920,1080",
      "--disable-gpu",
      "--disable-background-networking",
    ],
    { stdio: "ignore" },
  );

  await new Promise((r) => setTimeout(r, 1200));

  try {
    const listRes = await fetch(`http://127.0.0.1:${REMOTE_PORT}/json`);
    const targets = await listRes.json();
    const pageTarget = targets.find((t) => t.type === "page") || targets[0];
    const cdp = new SimpleCDP(pageTarget.webSocketDebuggerUrl);
    await cdp.connect();

    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await cdp.send("Network.enable");

    const sessionCookie = getSignedSessionCookie();
    console.log(`Setting session cookie for user 1...`);
    await cdp.send("Network.setCookie", {
      name: "deepvision_django_session",
      value: sessionCookie,
      url: BASE_URL,
      domain: "127.0.0.1",
      path: "/",
      httpOnly: true,
    });

    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: 1920,
      height: 1080,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await cdp.send("Page.navigate", { url: `${BASE_URL}/` });
    await cdp.wait(2000);

    // 2. Overview Dashboard
    console.log("Capturing Overview Dashboard...");
    await cdp.send("Page.navigate", { url: `${BASE_URL}/#overview` });
    await cdp.wait(1500);
    await cdp.screenshot("01_deepvision_3.0_overview_dashboard.png");

    // 3. Live Surveillance & 10 Canonical Navigation Destinations
    console.log("Capturing Live Surveillance...");
    await cdp.send("Page.navigate", {
      url: `${BASE_URL}/#surveillance?camera=4`,
    });
    await cdp.wait(2500);
    await cdp.screenshot("02_deepvision_3.0_live_surveillance_webcam0.png");

    // 4. Open Zone Editor Drawer
    console.log("Opening Security Perimeter Zone Editor...");
    await cdp.eval(`(() => {
      const btn = document.getElementById('btn-toggle-zone-editor');
      if (btn) btn.click();
    })()`);
    await cdp.wait(1000);

    // Click Webcam 0 Preset
    await cdp.eval(`(() => {
      const pbtn = document.getElementById('btn-preset-webcam-zone');
      if (pbtn) pbtn.click();
    })()`);
    await cdp.wait(800);
    await cdp.screenshot("03_deepvision_3.0_webcam0_zone_editor.png");

    // 5. Security Alerts Inbox
    console.log("Capturing Security Alerts Inbox...");
    await cdp.send("Page.navigate", {
      url: `${BASE_URL}/#security-center?tab=alerts`,
    });
    await cdp.wait(1500);
    await cdp.screenshot("04_deepvision_3.0_security_alerts.png");

    // 6. Cameras Management Grid
    console.log("Capturing Cameras Management Grid...");
    await cdp.send("Page.navigate", { url: `${BASE_URL}/#cameras` });
    await cdp.wait(1500);
    await cdp.screenshot("05_deepvision_3.0_cameras_inventory.png");

    // 7. Forensic Evidence Vault
    console.log("Capturing Evidence Vault...");
    await cdp.send("Page.navigate", {
      url: `${BASE_URL}/#security-center?tab=evidence`,
    });
    await cdp.wait(1500);
    await cdp.screenshot("06_deepvision_3.0_evidence_vault.png");

    console.log(
      "All DeepVision 3.0 evidence screenshots captured successfully.",
    );
  } finally {
    try {
      chromeProc.kill();
    } catch (_) {}
  }
}

main().catch(console.error);
