"""
DeepVision Dual-Run Release Gate Runner
Executes the full automated regression suite twice consecutively against the verified code state.
"""
import sys
import subprocess
from pathlib import Path

VENV_PYTHON = str(Path("D:/DeepVision/venv/Scripts/python.exe"))
SCRIPTS = [
    ("PASSWORD_RESET_ACCEPTANCE", "verification/test_password_reset_flow.py"),
    ("FULL_STACK_E2E", "verification/test_full_e2e.py"),
    ("SECURITY_AUDIT", "verification/test_security_audit.py"),
    ("CAMERA_HARDWARE_PIPELINE", "verification/test_complete_camera_pipeline.py"),
    ("COMPLETE_AUTH_OTP", "verification/test_complete_auth_otp.py"),
    ("DB_DASHBOARD_RECONCILIATION", "verification/reconcile_dashboard_db.py"),
]

def run_suite(iteration):
    print("\n" + "=" * 70)
    print(f"  RELEASE GATE ITERATION #{iteration} START")
    print("=" * 70)
    all_passed = True
    results = {}
    
    for name, script_path in SCRIPTS:
        cmd = [VENV_PYTHON, script_path]
        print(f"\n>> [{name}] Running {script_path}...")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            print(f"   [PASS] {name} completed successfully (exit code 0)")
            results[name] = "PASS"
        else:
            print(f"   [FAIL] {name} exited with code {proc.returncode}")
            print(proc.stdout[-500:] if proc.stdout else "")
            print(proc.stderr[-500:] if proc.stderr else "")
            results[name] = "FAIL"
            all_passed = False
            
    print("\n" + "-" * 70)
    print(f"  RELEASE GATE ITERATION #{iteration} SUMMARY: " + ("ALL PASSED" if all_passed else "FAILURES DETECTED"))
    print("-" * 70)
    for k, v in results.items():
        print(f"  {k:<35}: {v}")
    return all_passed

if __name__ == "__main__":
    iter_num = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    success = run_suite(iter_num)
    sys.exit(0 if success else 1)
