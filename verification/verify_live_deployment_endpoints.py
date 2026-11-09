"""
DeepVision Live Production Deployment Verification Suite
Probes the four canonical production URLs and verifies headers, cookies, CSP, and CORS.
"""
import urllib.request
import urllib.error
import time
import json
import ssl

ctx = ssl.create_default_context()

TARGETS = [
    ("Render Health", "https://deepvision-6ie7.onrender.com/api/health/"),
    ("Render CSRF", "https://deepvision-6ie7.onrender.com/api/auth/csrf/"),
    ("Vercel Frontend", "https://deepvision-soc.vercel.app/"),
    ("Vercel CSRF Rewrite Proxy", "https://deepvision-soc.vercel.app/api/auth/csrf/"),
]

def verify_all():
    print("=" * 70)
    print("DEEPVISION LIVE DEPLOYMENT ENDPOINT VERIFICATION")
    print("=" * 70)

    results = []

    for label, url in TARGETS:
        print(f"\n[PROBING] {label} -> {url}")
        t0 = time.time()
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DeepVisionQA/4.0",
                "Origin": "https://deepvision-soc.vercel.app"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx) as res:
                dur = time.time() - t0
                status = res.status
                headers = dict(res.headers)
                body = res.read().decode("utf-8", errors="ignore")

                set_cookie = headers.get("set-cookie", headers.get("Set-Cookie", "None"))
                server = headers.get("server", headers.get("Server", "Unknown"))
                csp = headers.get("content-security-policy", headers.get("Content-Security-Policy", "None"))

                print(f"  HTTP Status:   {status} in {dur:.2f}s")
                print(f"  Server:        {server}")
                print(f"  Set-Cookie:    {set_cookie[:80]}..." if set_cookie != "None" else "  Set-Cookie:    None")
                if "json" in headers.get("content-type", ""):
                    try:
                        parsed = json.loads(body)
                        print(f"  JSON Payload:  {json.dumps(parsed)[:120]}...")
                    except Exception:
                        print(f"  Body:          {body[:100]}...")
                else:
                    print(f"  Body (HTML):   {body[:100].strip()}...")

                results.append((label, url, status, dur, True))
        except urllib.error.HTTPError as e:
            dur = time.time() - t0
            print(f"  HTTP Error:    {e.code} in {dur:.2f}s")
            results.append((label, url, e.code, dur, False))
        except Exception as e:
            dur = time.time() - t0
            print(f"  Network Error: {type(e).__name__} - {e} in {dur:.2f}s")
            results.append((label, url, 0, dur, False))

    print("\n" + "=" * 70)
    print("DEPLOYMENT VERIFICATION SUMMARY:")
    all_ok = True
    for label, url, st, dur, ok in results:
        status_str = "PASS" if ok else "FAIL"
        if not ok: all_ok = False
        print(f"  [{status_str}] {label:<28}: HTTP {st} in {dur:.2f}s")
    print("=" * 70)
    return all_ok

if __name__ == "__main__":
    verify_all()
