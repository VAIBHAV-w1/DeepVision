"""
DeepVision Dual Consecutive Full Regression Harness
Executes two full consecutive passes across all 5 verification suites:
1. Django Account Unit Tests
2. CSP & Infinite Loader Guard Suite
3. Trilingual Localization Parity Audit
4. Complete 12-Step Authentication Lifecycle Suite
5. End-to-End Full-System Integration Suite
"""

import subprocess
import sys
import time

SUITES = [
    ("Django Accounts Tests", [sys.executable, "deepvision_django/manage.py", "test", "apps.accounts.tests", "--verbosity", "1"]),
    ("CSP & Loader Guard", [sys.executable, "verification/test_csp_and_startup_loader.py"]),
    ("Localization Audit", ["node", "verification/audit_complete_localization.cjs"]),
    ("Authentication Lifecycle", [sys.executable, "verification/test_auth_lifecycle_end_to_end.py"]),
    ("Full-System E2E", [sys.executable, "verification/test_e2e_full_system.py"]),
]

def run_single_pass(pass_num: int) -> bool:
    print("\n" + "=" * 70)
    print(f"REGRESSION PASS {pass_num} — START")
    print("=" * 70)

    pass_ok = True
    t0 = time.time()

    for name, cmd in SUITES:
        print(f"  [RUNNING] {name}...")
        t_suite = time.time()
        res = subprocess.run(cmd, capture_output=True, text=True)
        dur = time.time() - t_suite
        if res.returncode == 0:
            print(f"  [PASS] {name} in {dur:.2f}s")
        else:
            print(f"  [FAIL] {name} in {dur:.2f}s")
            err_msg = res.stderr.strip() or res.stdout.strip()
            print(f"         Error: {err_msg[:250]}")
            pass_ok = False

    tot_dur = time.time() - t0
    status_str = "PASSED (5/5 suites)" if pass_ok else "FAILED"
    print("-" * 70)
    print(f"REGRESSION PASS {pass_num} RESULT: {status_str} in {tot_dur:.2f}s")
    print("=" * 70)
    return pass_ok

def main():
    print("=" * 70)
    print("DEEPVISION MASTER DUAL REGRESSION HARNESS")
    print("=" * 70)

    pass1 = run_single_pass(1)
    if not pass1:
        print("\nPass 1 failed; aborting Pass 2.")
        sys.exit(1)

    print("\nPausing 1 second before Pass 2...")
    time.sleep(1)

    pass2 = run_single_pass(2)
    if not pass2:
        print("\nPass 2 failed!")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("DUAL REGRESSION SUMMARY: 2/2 CONSECUTIVE PASSES FULLY VERIFIED")
    print("=" * 70)
    sys.exit(0)

if __name__ == "__main__":
    main()
