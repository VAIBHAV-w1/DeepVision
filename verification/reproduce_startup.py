import sys
import time
import json
import asyncio
import subprocess
import urllib.request
import websockets

TARGET_URL = "https://vsw-deepvision.vercel.app"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

async def test_session(simulate_cookie=False):
    port = 9227
    cmd = [
        CHROME_PATH,
        "--headless=new",
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--disable-gpu",
        "--window-size=1920,1080",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await asyncio.sleep(1.5)
    
    try:
        # Get new tab
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new", data=b"", method="PUT")
        with urllib.request.urlopen(req) as resp:
            tab = json.loads(resp.read().decode())
            ws_url = tab["webSocketDebuggerUrl"]

        ws = await websockets.connect(ws_url, max_size=20_000_000)
        msg_id = 0
        responses = {}

        async def send(method, params=None):
            nonlocal msg_id
            msg_id += 1
            cid = msg_id
            payload = {"id": cid, "method": method, "params": params or {}}
            await ws.send(json.dumps(payload))
            return cid

        logs = []
        network = []

        async def listener():
            try:
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if "id" in data:
                        responses[data["id"]] = data
                    method = data.get("method", "")
                    if method == "Runtime.consoleAPICalled":
                        p = data.get("params", {})
                        text = " ".join([str(a.get("value", a.get("description", ""))) for a in p.get("args", [])])
                        logs.append(f"[CONSOLE {p.get('type')}] {text}")
                    elif method == "Runtime.exceptionThrown":
                        p = data.get("params", {})
                        det = p.get("exceptionDetails", {})
                        logs.append(f"[EXCEPTION] {det.get('text')} {det.get('exception', {}).get('description')}")
                    elif method == "Log.entryAdded":
                        entry = data.get("params", {}).get("entry", {})
                        logs.append(f"[LOG {entry.get('level')} / {entry.get('source')}] {entry.get('text')}")
                    elif method == "Network.responseReceived":
                        res = data.get("params", {}).get("response", {})
                        network.append(f"[HTTP {res.get('status')}] {res.get('url')}")
            except asyncio.CancelledError:
                pass
            except Exception as e:
                pass

        listen_task = asyncio.create_task(listener())

        await send("Runtime.enable")
        await send("Log.enable")
        await send("Network.enable")
        await send("Page.enable")

        if simulate_cookie:
            # Set cookie
            await send("Network.setCookie", {
                "name": "sessionid",
                "value": "fake_or_real_session",
                "domain": "vsw-deepvision.vercel.app",
                "path": "/"
            })

        print(f"\n---> Navigating to {TARGET_URL} (simulate_cookie={simulate_cookie})")
        await send("Page.navigate", {"url": TARGET_URL})
        await asyncio.sleep(4)

        eval_id = await send("Runtime.evaluate", {
            "expression": """
                ({
                    bodyText: document.body.innerText,
                    hasLoader: !!document.body.innerText.includes('Initializing DeepVision SOC...'),
                    rootChildren: document.getElementById('root')?.children.length,
                    activeTheme: document.documentElement.getAttribute('data-theme')
                })
            """,
            "returnByValue": True
        })
        await asyncio.sleep(1)

        result = responses.get(eval_id, {}).get("result", {}).get("result", {}).get("value")
        print("DOM State:", json.dumps(result, indent=2))
        print("Logs count:", len(logs))
        for l in logs:
            print("  ", l)
        print("Network count:", len(network))
        for n in network:
            print("  ", n)

        listen_task.cancel()
        await ws.close()
    finally:
        proc.kill()

async def main():
    print("=== TEST 1: FRESH VISIT ===")
    await test_session(simulate_cookie=False)

if __name__ == "__main__":
    asyncio.run(main())
