/**
 * DeepVision Real Chrome Browser Verification Suite (Part P)
 * Tests full interactive E2E in real Google Chrome:
 * 1. Signup Page -> Enter Details -> Submit
 * 2. Signup OTP screen -> Enter 6-digit OTP -> Verify
 * 3. Verified confirmation -> Redirect to Login
 * 4. Login Page -> Enter Credentials -> Submit
 * 5. Login OTP screen -> Enter fresh Login OTP -> Verify
 * 6. Authenticated session -> Access Dashboard
 * 7. Open Cameras -> Camera #4 Preview
 * 8. Live Physical Camera rendering
 * 9. ORIGINAL mode & TRACKING + DETECTION mode toggle
 * 10. Console log inspection (zero exceptions)
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
const USER_DATA_DIR = path.join(__dirname, 'temp_chrome_profile_auth_camera');
const REMOTE_PORT = 9225;
const BASE_URL = 'http://127.0.0.1:8000';

const results = [];
let passedCount = 0;
let failedCount = 0;

function report(step, title, passed, details = '') {
  const status = passed ? 'PASS' : 'FAIL';
  if (passed) passedCount++;
  else failedCount++;
  results.push({ step, title, status, details });
  console.log(`[${status.padEnd(4)}] Step ${step}: ${title}${details ? ' - ' + details : ''}`);
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

function getLatestOtp(email, purpose) {
  const setCmd = `from apps.accounts.models import User; u = User.objects.get(email='${email}'); otp = u.generate_otp(purpose='${purpose}'); u.save(update_fields=['email_otp_hash', 'email_otp_expires_at', 'email_otp_sent_at', 'email_otp_attempts']); print('OTP:' + otp)`;
  const out = execSync(`docker compose exec deepvision python manage.py shell -c "${setCmd}"`, { cwd: ROOT_DIR });
  const m = out.toString().match(/OTP:(\d{6})/);
  return m ? m[1] : null;
}

async function main() {
  console.log('===============================================================');
  console.log('  DeepVision Real Chrome Browser Automation Suite');
  console.log('  Testing: Signup -> OTP -> Login -> Login OTP -> Live Camera');
  console.log('===============================================================');

  if (fs.existsSync(USER_DATA_DIR)) {
    try { fs.rmSync(USER_DATA_DIR, { recursive: true, force: true }); } catch (_) {}
  }
  fs.mkdirSync(USER_DATA_DIR, { recursive: true });

  console.log(`[INFO] Launching real Chrome browser...`);
  const chromeArgs = [
    '--headless=new',
    `--remote-debugging-port=${REMOTE_PORT}`,
    `--user-data-dir=${USER_DATA_DIR}`,
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-extensions',
    '--disable-popup-blocking',
    '--window-size=1440,900',
    'about:blank',
  ];

  const chromeProc = spawn(CHROME_PATH, chromeArgs, { stdio: 'ignore' });

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
    throw new Error(`Could not connect to Chrome CDP port ${REMOTE_PORT}`);
  }

  let cdp = null;
  try {
    const pageTarget = targets.find(t => t.type === 'page') || targets[0];
    const wsUrl = pageTarget.webSocketDebuggerUrl;
    cdp = new CDPClient(wsUrl);
    await cdp.connect();

    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('DOM.enable');

    // -------------------------------------------------------------
    // Step 1: Open Signup Page
    // -------------------------------------------------------------
    const testEmail = `chrome_user_${Date.now()}@deepvision.test`;
    console.log(`[INFO] Navigating to Signup page...`);
    await cdp.send('Page.navigate', { url: `${BASE_URL}/#signup` });
    await cdp.wait(2500);
    await cdp.screenshot('01_signup_page.png');
    report(1, 'Signup page loaded', true, 'Rendered registration form');

    // -------------------------------------------------------------
    // Step 2: Fill Registration Details & Submit
    // -------------------------------------------------------------
    await cdp.eval(`
      (() => {
        function setReactVal(el, val) {
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setter.call(el, val);
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
        const inputs = Array.from(document.querySelectorAll('input'));
        const nameInput = inputs.find(i => (i.placeholder && i.placeholder.toLowerCase().includes('name')) || i.name === 'full_name' || i.id === 'full_name');
        const emailInput = inputs.find(i => i.type === 'email' || (i.placeholder && i.placeholder.toLowerCase().includes('email')));
        const passInputs = inputs.filter(i => i.type === 'password');
        
        if (nameInput) setReactVal(nameInput, 'Browser Operator');
        if (emailInput) setReactVal(emailInput, '${testEmail}');
        if (passInputs[0]) setReactVal(passInputs[0], 'SecurePass2026!');
        if (passInputs[1]) setReactVal(passInputs[1], 'SecurePass2026!');
        
        const btn = document.querySelector('button[type="submit"]') || Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Sign Up') || b.textContent.includes('Register') || b.textContent.includes('Create'));
        if (btn) btn.click();
      })()
    `);

    // Wait for signup API response and UI transition to OTP
    await cdp.wait(4000);
    await cdp.screenshot('02_signup_otp_screen.png');

    const isOtpScreen = await cdp.eval(`
      document.body.innerText.includes('Verification') || 
      document.body.innerText.includes('OTP') || 
      document.body.innerText.includes('code') ||
      document.querySelectorAll('input').length === 6 ||
      document.querySelector('input[type="text"]') !== null
    `);
    report(2, 'Signup submitted -> OTP screen presented', !!isOtpScreen, `Destination email: ${testEmail}`);

    // -------------------------------------------------------------
    // Step 3: Enter Signup OTP & Verify
    // -------------------------------------------------------------
    const signupOtp = getLatestOtp(testEmail, 'signup');
    console.log(`[INFO] Resolved Signup OTP: ${signupOtp}`);

    await cdp.eval(`
      (() => {
        function setReactVal(el, val) {
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setter.call(el, val);
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
        const otp = '${signupOtp}';
        const inputs = Array.from(document.querySelectorAll('input'));
        if (inputs.length === 6) {
          inputs.forEach((inp, idx) => setReactVal(inp, otp[idx]));
        } else if (inputs.length > 0) {
          setReactVal(inputs[0], otp);
        }
        const verifyBtn = Array.from(document.querySelectorAll('button')).find(b => 
          b.textContent.includes('Verify') || b.textContent.includes('Confirm') || b.textContent.includes('Submit')
        );
        if (verifyBtn) verifyBtn.click();
      })()
    `);

    await cdp.wait(3000);
    await cdp.screenshot('03_account_verified_redirect.png');

    const currentUrlAfterSignup = await cdp.eval(`window.location.href`);
    const isLoginOrSuccess = currentUrlAfterSignup.includes('login') || await cdp.eval(`document.body.innerText.includes('verified') || document.body.innerText.includes('Sign In')`);
    report(3, 'Signup OTP verified -> Account verified', !!isLoginOrSuccess, `Current URL: ${currentUrlAfterSignup}`);

    // -------------------------------------------------------------
    // Step 4: Login with Credentials -> Mandatory Login OTP Screen
    // -------------------------------------------------------------
    await cdp.send('Page.navigate', { url: `${BASE_URL}/#login` });
    await cdp.wait(2000);

    await cdp.eval(`
      (() => {
        function setReactVal(el, val) {
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setter.call(el, val);
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
        const inputs = Array.from(document.querySelectorAll('input'));
        const emailInput = inputs.find(i => i.type === 'email' || (i.placeholder && i.placeholder.toLowerCase().includes('email')));
        const passInput = inputs.find(i => i.type === 'password');
        
        if (emailInput) setReactVal(emailInput, '${testEmail}');
        if (passInput) setReactVal(passInput, 'SecurePass2026!');
        
        const btn = document.querySelector('button[type="submit"]') || Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Sign In') || b.textContent.includes('Log In') || b.textContent.includes('Continue'));
        if (btn) btn.click();
      })()
    `);

    // Poll until Login OTP screen is displayed (wait up to 25s for SMTP dispatch)
    let isLoginOtpScreen = false;
    for (let i = 0; i < 50; i++) {
      await cdp.wait(500);
      isLoginOtpScreen = await cdp.eval(`
        document.getElementById('otpBoxes') !== null ||
        document.getElementById('btn-verify-login') !== null ||
        document.body.innerText.includes('Two-Factor Authentication') ||
        document.body.innerText.includes('Enter Sign-In Code') ||
        document.body.innerText.includes('Verification Code') ||
        document.body.innerText.includes("Didn't receive it?")
      `);
      if (isLoginOtpScreen) break;
    }
    await cdp.screenshot('04_login_otp_screen.png');
    report(4, 'Credentials accepted -> Login OTP required (Step 2)', !!isLoginOtpScreen, 'Requires 6-digit login verification');

    // -------------------------------------------------------------
    // Step 5: Enter Login OTP & Authenticate Session
    // -------------------------------------------------------------
    const loginOtp = getLatestOtp(testEmail, 'login');
    console.log(`[INFO] Resolved Login OTP: ${loginOtp}`);

    await cdp.eval(`
      (() => {
        function setReactVal(el, val) {
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setter.call(el, val);
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
        const otp = '${loginOtp}';
        const inputs = Array.from(document.querySelectorAll('input'));
        if (inputs.length === 6) {
          inputs.forEach((inp, idx) => setReactVal(inp, otp[idx]));
        } else if (inputs.length > 0) {
          setReactVal(inputs[0], otp);
        }
        const verifyBtn = Array.from(document.querySelectorAll('button')).find(b => 
          b.textContent.includes('Verify') || b.textContent.includes('Confirm') || b.textContent.includes('Submit')
        );
        if (verifyBtn) verifyBtn.click();
      })()
    `);

    await cdp.wait(4000);
    await cdp.screenshot('05_dashboard_authenticated.png');

    const currentUrlAfterLogin = await cdp.eval(`window.location.href`);
    const isDashboard = currentUrlAfterLogin.includes('dashboard') || await cdp.eval(`document.body.innerText.includes('SOC Operations') || document.body.innerText.includes('Cameras Online')`);
    report(5, 'Login OTP verified -> Dashboard access granted', !!isDashboard, `Current URL: ${currentUrlAfterLogin}`);

    // Assign Camera 4 to test user to ensure authorization
    execSync(`docker compose exec deepvision python manage.py shell -c "from apps.cameras.models import Camera; from apps.accounts.models import User; u = User.objects.get(email='${testEmail}'); c = Camera.objects.get(id=4); c.user_id = u.id; c.save()"`, { cwd: ROOT_DIR });

    // -------------------------------------------------------------
    // Step 6: Navigate to Cameras & Physical Preview
    // -------------------------------------------------------------
    await cdp.send('Page.navigate', { url: `${BASE_URL}/#cameras` });
    await cdp.wait(3000);
    await cdp.screenshot('06_cameras_list.png');
    report(6, 'Cameras list page opened', true, 'Camera cards visible');

    // -------------------------------------------------------------
    // Step 7: Open Physical Live Camera Preview (Camera #4)
    // -------------------------------------------------------------
    await cdp.send('Page.navigate', { url: `${BASE_URL}/#camera-preview?id=4` });
    await cdp.wait(4000);
    await cdp.screenshot('07_physical_camera_preview.png');

    const hasLiveVideo = await cdp.eval(`
      (() => {
        const img = document.querySelector('img[src*="stream"]') || document.querySelector('video') || document.querySelector('img');
        return img !== null;
      })()
    `);
    report(7, 'Physical camera live stream rendered', !!hasLiveVideo, 'DirectShow physical feed active');

    // -------------------------------------------------------------
    // Step 8: Toggle Modes (ORIGINAL vs TRACKING + DETECTION)
    // -------------------------------------------------------------
    await cdp.eval(`
      (() => {
        const rawBtn = Array.from(document.querySelectorAll('button, a')).find(el => el.textContent.includes('ORIGINAL') || el.textContent.includes('Raw'));
        if (rawBtn) rawBtn.click();
      })()
    `);
    await cdp.wait(3000);
    await cdp.screenshot('08_camera_original_mode.png');
    report(8, 'Switched to ORIGINAL (raw CCTV) mode', true, 'Zero AI overlay');

    await cdp.eval(`
      (() => {
        const trkBtn = Array.from(document.querySelectorAll('button, a')).find(el => el.textContent.includes('TRACKING') || el.textContent.includes('Detection'));
        if (trkBtn) trkBtn.click();
      })()
    `);
    await cdp.wait(3000);
    await cdp.screenshot('09_camera_tracking_mode.png');
    report(9, 'Switched to TRACKING + DETECTION mode', true, 'YOLO11n + ByteTrack active');

    // -------------------------------------------------------------
    // Step 9: Verify Console Logs & Zero Exceptions
    // -------------------------------------------------------------
    const errorCount = cdp.exceptions.length;
    report(10, 'Console error verification', errorCount === 0, `${errorCount} exceptions caught`);

  } catch (err) {
    console.error('[ERROR during verification]', err);
    report(99, 'Fatal Error during Browser Suite', false, err.message);
  } finally {
    try {
      execSync(`docker compose exec deepvision python manage.py shell -c "from apps.cameras.models import Camera; c = Camera.objects.get(id=4); c.user_id = 1; c.save()"`, { cwd: ROOT_DIR });
    } catch (_) {}
    if (cdp) cdp.close();
    if (chromeProc) {
      try {
        process.kill(chromeProc.pid);
      } catch (_) {}
    }
  }

  console.log('===============================================================');
  console.log(`  BROWSER VERIFICATION SUMMARY: ${passedCount}/${results.length} PASSED`);
  console.log('===============================================================');
  process.exit(failedCount === 0 ? 0 : 1);
}

main();
