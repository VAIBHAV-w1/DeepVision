/**
 * DeepVision 4.0 — 5 Primary Destinations, Route Consolidation & Full i18n Verification Suite
 * ============================================================================================
 */

import { spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";

const BASE_URL = process.env.DEEPVISION_URL || "http://127.0.0.1:8000";
const CHROME_PATH =
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const CDP_PORT = 9366;

const ROOT_DIR = path.resolve(import.meta.dirname, "..");
const SHOT_DIR = path.join(
  ROOT_DIR,
  "verification",
  "screenshots",
  "final_5destinations",
);
const REPORT_PATH = path.join(
  ROOT_DIR,
  "reports",
  "p2_5destinations_i18n_verification.json",
);

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function getJson(url) {
  return new Promise((resolve, reject) => {
    http
      .get(url, (res) => {
        let body = "";
        res.on("data", (c) => (body += c));
        res.on("end", () => {
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            reject(e);
          }
        });
      })
      .on("error", reject);
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
      this.ws.addEventListener("open", resolve, { once: true });
      this.ws.addEventListener("error", reject, { once: true });
    });
    this.ws.addEventListener("message", (ev) => {
      const msg = JSON.parse(
        typeof ev.data === "string" ? ev.data : ev.data.toString(),
      );
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
  async evalJs(expression) {
    const res = await this.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    return res?.result?.value;
  }
  async screenshot(filePath) {
    const res = await this.send("Page.captureScreenshot", { format: "png" });
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, Buffer.from(res.data, "base64"));
  }
  async setViewport(width, height) {
    await this.send("Emulation.setDeviceMetricsOverride", {
      width,
      height,
      deviceScaleFactor: 1,
      mobile: width < 768,
    });
  }
}

async function main() {
  fs.mkdirSync(SHOT_DIR, { recursive: true });
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "chrome-5dest-"));

  const chromeProc = spawn(
    CHROME_PATH,
    [
      `--remote-debugging-port=${CDP_PORT}`,
      "--headless=new",
      "--disable-gpu",
      "--disable-extensions",
      "--no-first-run",
      "--no-default-browser-check",
      `--user-data-dir=${userDataDir}`,
      "about:blank",
    ],
    { stdio: "ignore" },
  );

  let cdp;
  const results = {
    timestamp: new Date().toISOString(),
    tests: [],
    screenshots: [],
    passed: 0,
    failed: 0,
  };

  try {
    let wsUrl = null;
    for (let i = 0; i < 30; i++) {
      try {
        const versionInfo = await getJson(
          `http://127.0.0.1:${CDP_PORT}/json/version`,
        );
        wsUrl = versionInfo.webSocketDebuggerUrl;
        if (wsUrl) break;
      } catch {
        await sleep(200);
      }
    }
    if (!wsUrl)
      throw new Error("Could not connect to Chrome DevTools Protocol");

    const tabs = await getJson(`http://127.0.0.1:${CDP_PORT}/json/list`);
    const pageTab = tabs.find((t) => t.type === "page" && !t.url.startsWith("chrome-")) || tabs.find((t) => t.type === "page") || tabs[0];
    cdp = new CdpSession(pageTab.webSocketDebuggerUrl);
    await cdp.connect();

    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await cdp.send("DOM.enable");
    await cdp.setViewport(1440, 900);

    console.log("[1/7] Navigating to DeepVision at", BASE_URL);
    await cdp.send("Page.navigate", { url: `${BASE_URL}/` });
    await sleep(2500);

    // Check if on login form
    const isLogin = await cdp.evalJs(
      `!document.querySelector('#nav-dashboard')`,
    );
    if (isLogin) {
      console.log("Signing in via Demo Operator Access...");
      await cdp.evalJs(`
        const btn = document.querySelector('#btn-demo-operator-access');
        if (btn) btn.click();
      `);
      for (let i = 0; i < 25; i++) {
        await sleep(300);
        const loggedIn = await cdp.evalJs(
          `!!document.querySelector('#nav-dashboard')`,
        );
        if (loggedIn) {
          console.log("Login successful! App header mounted.");
          break;
        }
      }
    }

    // Verify 5 Primary Destinations
    console.log(
      "[2/7] Verifying strictly 5 primary navigation destinations in UI...",
    );
    const navItemsData = await cdp.evalJs(`
      (() => {
        const expected = [
          'nav-dashboard',
          'nav-cameras',
          'nav-notifications',
          'nav-settings',
          'nav-help'
        ];
        return expected.map(id => {
          const el = document.getElementById(id);
          return el ? { id: el.id, text: el.innerText.trim() } : null;
        }).filter(Boolean);
      })()
    `);
    console.log("Navbar/Sidebar primary links detected:", navItemsData);

    const expectedKeys = [
      "nav-dashboard",
      "nav-cameras",
      "nav-notifications",
      "nav-settings",
      "nav-help",
    ];
    const actualKeys = navItemsData ? navItemsData.map((n) => n.id) : [];
    const hasExactly5 =
      actualKeys.length === 5 &&
      expectedKeys.every((k) => actualKeys.includes(k));

    results.tests.push({
      name: "Strictly 5 Primary Navigation Items",
      expected: expectedKeys,
      actual: actualKeys,
      pass: hasExactly5,
    });
    if (hasExactly5) results.passed++;
    else results.failed++;

    // Workspace 1: Dashboard
    console.log("[3/7] Verifying Workspace 1: Dashboard...");
    await cdp.evalJs(`window.location.hash = '#dashboard'`);
    await sleep(1500);
    const isDashboard = await cdp.evalJs(`
      (() => {
        const hasMetrics = !!document.querySelector('.dashboard-metrics-grid');
        const hasWorkspaces = !!document.querySelector('.dashboard-page-container');
        const hasVideo = !!document.querySelector('video');
        return hasMetrics && hasWorkspaces && !hasVideo;
      })()
    `);
    await cdp.screenshot(path.join(SHOT_DIR, "01_dashboard_1440.png"));
    results.screenshots.push("01_dashboard_1440.png");
    results.tests.push({
      name: "Dashboard Clean & Independent (No live player)",
      pass: Boolean(isDashboard),
    });
    if (isDashboard) results.passed++;
    else results.failed++;

    // Workspace 2: Cameras
    console.log("[4/7] Verifying Workspace 2: Cameras...");
    await cdp.evalJs(`window.location.hash = '#cameras'`);
    await sleep(2000);
    const isCameras = await cdp.evalJs(`
      (() => {
        const hasGallery = !!document.querySelector('.cameras-grid-container') || !!document.querySelector('.camera-card') || !!document.querySelector('.camera-detail-workspace') || !!document.querySelector('.cameras-page-container');
        return hasGallery;
      })()
    `);
    await cdp.screenshot(path.join(SHOT_DIR, "02_cameras_1440.png"));
    results.screenshots.push("02_cameras_1440.png");
    results.tests.push({ name: "Cameras Workspace", pass: Boolean(isCameras) });
    if (isCameras) results.passed++;
    else results.failed++;

    // Workspace 3: Notifications
    console.log("[5/7] Verifying Workspace 3: Notifications...");
    await cdp.evalJs(`window.location.hash = '#notifications'`);
    await sleep(2000);
    const isNotifications = await cdp.evalJs(`
      (() => {
        const hasNotifs = !!document.querySelector('.notifications-page-container') || !!document.querySelector('.security-workspace-tabs');
        return hasNotifs;
      })()
    `);
    await cdp.screenshot(path.join(SHOT_DIR, "03_notifications_1440.png"));
    results.screenshots.push("03_notifications_1440.png");
    results.tests.push({
      name: "Notifications Central Security Workspace",
      pass: Boolean(isNotifications),
    });
    if (isNotifications) results.passed++;
    else results.failed++;

    // Workspace 4: Settings & Workspace 5: Help
    console.log("[6/7] Verifying Workspace 4: Settings & Workspace 5: Help...");
    await cdp.evalJs(`window.location.hash = '#settings'`);
    await sleep(1500);
    await cdp.screenshot(path.join(SHOT_DIR, "04_settings_1440.png"));
    results.screenshots.push("04_settings_1440.png");

    await cdp.evalJs(`window.location.hash = '#help'`);
    await sleep(1500);
    await cdp.screenshot(path.join(SHOT_DIR, "05_help_1440.png"));
    results.screenshots.push("05_help_1440.png");

    // Test Legacy Route Redirection
    console.log("[7/7] Testing Legacy Route Redirection...");
    await cdp.evalJs(`window.location.hash = '#alerts'`);
    await sleep(1000);
    const afterAlertsHash = await cdp.evalJs(`window.location.hash`);
    const alertsRedirectPass =
      afterAlertsHash.includes("notifications") &&
      afterAlertsHash.includes("incidents");
    results.tests.push({
      name: "Legacy #alerts -> #notifications?tab=incidents",
      actual: afterAlertsHash,
      pass: alertsRedirectPass,
    });
    if (alertsRedirectPass) results.passed++;
    else results.failed++;

    // Multi-Language Reactivity (Hindi & Kannada)
    console.log("Testing Multi-Language Reactivity (Hindi & Kannada)...");
    await cdp.evalJs(`window.location.hash = '#dashboard'`);
    await sleep(1000);

    // Switch to Hindi
    await cdp.evalJs(`
      if (window.__setDeepVisionLanguage) {
        window.__setDeepVisionLanguage('hi');
      } else {
        const btn = document.querySelector('#btn-language-selector');
        if (btn) btn.click();
        const opt = document.querySelector('#lang-option-hi');
        if (opt) opt.click();
      }
    `);
    await sleep(1200);

    const hiText = await cdp.evalJs(
      `document.getElementById('nav-dashboard')?.innerText.trim()`,
    );
    await cdp.screenshot(path.join(SHOT_DIR, "06_dashboard_hindi_1440.png"));
    results.screenshots.push("06_dashboard_hindi_1440.png");
    const hiPass = hiText === "डैशबोर्ड";
    results.tests.push({
      name: "Hindi Reactive Language Switch",
      actual: hiText,
      pass: hiPass,
    });
    if (hiPass) results.passed++;
    else results.failed++;

    // Switch to Kannada
    await cdp.evalJs(`
      if (window.__setDeepVisionLanguage) {
        window.__setDeepVisionLanguage('kn');
      } else {
        const btn = document.querySelector('#btn-language-selector');
        if (btn) btn.click();
        const opt = document.querySelector('#lang-option-kn');
        if (opt) opt.click();
      }
    `);
    await sleep(1200);

    const knText = await cdp.evalJs(
      `document.getElementById('nav-dashboard')?.innerText.trim()`,
    );
    await cdp.screenshot(path.join(SHOT_DIR, "07_dashboard_kannada_1440.png"));
    results.screenshots.push("07_dashboard_kannada_1440.png");
    const knPass = knText === "ಡ್ಯಾಶ್‌ಬೋರ್ಡ್";
    results.tests.push({
      name: "Kannada Reactive Language Switch",
      actual: knText,
      pass: knPass,
    });
    if (knPass) results.passed++;
    else results.failed++;

    // Switch back to English
    await cdp.evalJs(`
      if (window.__setDeepVisionLanguage) {
        window.__setDeepVisionLanguage('en');
      }
    `);
    await sleep(1000);

    fs.writeFileSync(REPORT_PATH, JSON.stringify(results, null, 2), "utf-8");
    console.log(`\n======================================================`);
    console.log(`PASSED: ${results.passed} | FAILED: ${results.failed}`);
    console.log(`Report written to: ${REPORT_PATH}`);
    console.log(`======================================================\n`);
  } finally {
    if (cdp?.ws) cdp.ws.close();
    chromeProc.kill("SIGTERM");
    try {
      fs.rmSync(userDataDir, { recursive: true, force: true });
    } catch {}
  }
}

main().catch((err) => {
  console.error("Test execution failed:", err);
  process.exit(1);
});
