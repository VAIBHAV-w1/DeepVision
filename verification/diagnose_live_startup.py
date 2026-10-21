import os
import sys
import time
import json
import asyncio
import subprocess
import urllib.request
import websockets

TARGET_URL = "https://vsw-deepvision.vercel.app"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
TEMP_USER_DATA = os.path.join(os.environ.get("TEMP", "C:\\Temp"), f"deepvision_diag_{int(time.time())}")

async def main():
    cmd = [
        CHROME_PATH,
        "--headless=new",
        "--remote-debugging-port=9225",
        f"--user-data-dir={TEMP_USER_DATA}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-gpu",
        "--window-size=1920,1080",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws_url = None
        for _ in range(30):
            try:
                time.sleep(0.3)
                with urllib.request.urlopen("http://127.0.0.1:9225/json/version", timeout=1) as resp:
                    info = json.loads(resp.read().decode())
                    ws_url = info.get("webSocketDebuggerUrl")
                    break
            except Exception:
                pass
        
        with urllib.request.urlopen("http://127.0.0.1:9225/json/list", timeout=2) as resp:
            targets = json.loads(resp.read().decode())
            page_ws = targets[0].get("webSocketDebuggerUrl")
        
        ws = await websockets.connect(page_ws, max_size=20_000_000)
        msg_id = 0
        async def send(method, params=None):
            nonlocal msg_id
            msg_id += 1
            cur = msg_id
            payload = {"id": cur, "method": method, "params": params or {}}
            await ws.send(json.dumps(payload))
            return cur

        console_messages = []
        network_events = []
        security_events = []

        async def listen():
            try:
                while True:
                    raw = await ws.recv()
                    data = json.loads(raw)
                    method = data.get("method", "")
                    if method == "Runtime.consoleAPICalled":
                        console_messages.append(data.get("params"))
                    elif method == "Runtime.exceptionThrown":
                        console_messages.append({"type": "exception", "details": data.get("params")})
                    elif method == "Log.entryAdded":
                        console_messages.append({"type": "log_entry", "details": data.get("params")})
                    elif method == "Network.requestWillBeSent":
                        req = data.get("params", {}).get("request", {})
                        network_events.append({"type": "req", "url": req.get("url"), "method": req.get("method")})
                    elif method == "Network.responseReceived":
                        res = data.get("params", {}).get("response", {})
                        network_events.append({"type": "res", "url": res.get("url"), "status": res.get("status")})
                    elif method == "Network.loadingFailed":
                        network_events.append({"type": "failed", "params": data.get("params")})
                    elif "Security." in method:
                        security_events.append(data)
            except Exception:
                pass

        listen_task = asyncio.create_task(listen())

        await send("Runtime.enable")
        await send("Log.enable")
        await send("Network.enable")
        await send("Page.enable")
        await send("Security.enable")

        print(f"Navigating to {TARGET_URL}...")
        await send("Page.navigate", {"url": TARGET_URL})

        # Wait for 6 seconds to observe full startup
        await asyncio.sleep(6)

        # Inspect DOM state
        eval_id = await send("Runtime.evaluate", {
            "expression": """
                ({
                    url: window.location.href,
                    title: document.title,
                    bodyText: document.body.innerText.substring(0, 500),
                    rootHTML: document.getElementById('root')?.innerHTML.substring(0, 500),
                    localStorage: Object.keys(localStorage),
                    scripts: Array.from(document.querySelectorAll('script')).map(s => s.src || s.textContent.substring(0, 100))
                })
            """,
            "returnByValue": True
        })

        await asyncio.sleep(1)

        print("\n=== CONSOLE / LOG MESSAGES ===")
        for cm in console_messages:
            print(json.dumps(cm, indent=2))

        print("\n=== NETWORK EVENTS ===")
        for ne in network_events:
            print(ne)

        listen_task.cancel()
        await ws.close()
    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(main())
