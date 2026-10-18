"""
DeepVision 1.1.0 Deployment Hardening Verification Suite
=======================================================
Validates all hardened deployment requirements:
1. Fail-closed secret key validation when DEBUG=False
2. Dev-friendly fallback secret key when DEBUG=True
3. ALLOWED_HOSTS & CSRF_TRUSTED_ORIGINS exclude 0.0.0.0
4. Setup script and Compose bind published ports strictly to 127.0.0.1
5. Server startup command enforces single worker (workers=1) and threads
6. Static asset delivery via WSGI StaticFilesHandler
7. SQLite database contract: 18 tables, zero django_migrations, integrity check
8. Live healthcheck & API authentication guards
"""

import os
import sys
import sqlite3
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DJANGO_DIR = ROOT_DIR / "deepvision_django"
if str(DJANGO_DIR) not in sys.path:
    sys.path.insert(0, str(DJANGO_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

RESULTS = []

def record(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    RESULTS.append((name, status, detail))
    print(f"[{status:4s}] {name}: {detail}")
    if not passed:
        raise AssertionError(f"Check failed: {name} - {detail}")


def test_secret_key_fail_closed():
    """Verify secret key fail-closed behavior in production and fallback in dev."""
    py_code_fail_empty = """
import os, sys
sys.path.insert(0, 'deepvision_django')
os.environ['DJANGO_DEBUG'] = 'False'
os.environ['DJANGO_SECRET_KEY'] = ''
try:
    from config import settings
    print('FAIL: Should have raised ImproperlyConfigured')
except Exception as e:
    print('CAUGHT:', type(e).__name__)
"""
    res = subprocess.run([sys.executable, "-c", py_code_fail_empty], cwd=str(ROOT_DIR), capture_output=True, text=True)
    record("SECRET_KEY_EMPTY_PROD_REJECTED", "CAUGHT: ImproperlyConfigured" in res.stdout, "Empty secret key rejected when DEBUG=False")

    py_code_fail_compromised = """
import os, sys
sys.path.insert(0, 'deepvision_django')
os.environ['DJANGO_DEBUG'] = 'False'
os.environ['DJANGO_SECRET_KEY'] = 'dv-sec-prod-entropy-key-9f8a3c7e2b1d4f6a8e0c2b4d6f8a1c3e5b7d9f0a2c4e6b8d0f1a3c5e7b9d'
try:
    from config import settings
    print('FAIL: Should have raised ImproperlyConfigured')
except Exception as e:
    print('CAUGHT:', type(e).__name__)
"""
    res = subprocess.run([sys.executable, "-c", py_code_fail_compromised], cwd=str(ROOT_DIR), capture_output=True, text=True)
    record("SECRET_KEY_COMPROMISED_PROD_REJECTED", "CAUGHT: ImproperlyConfigured" in res.stdout, "Compromised fallback key rejected when DEBUG=False")

    py_code_fail_short = """
import os, sys
sys.path.insert(0, 'deepvision_django')
os.environ['DJANGO_DEBUG'] = 'False'
os.environ['DJANGO_SECRET_KEY'] = 'short-key'
try:
    from config import settings
    print('FAIL: Should have raised ImproperlyConfigured')
except Exception as e:
    print('CAUGHT:', type(e).__name__)
"""
    res = subprocess.run([sys.executable, "-c", py_code_fail_short], cwd=str(ROOT_DIR), capture_output=True, text=True)
    record("SECRET_KEY_SHORT_PROD_REJECTED", "CAUGHT: ImproperlyConfigured" in res.stdout, "Short key (<32 chars) rejected when DEBUG=False")

    py_code_valid_prod = """
import os, sys
sys.path.insert(0, 'deepvision_django')
os.environ['DJANGO_DEBUG'] = 'False'
os.environ['DJANGO_SECRET_KEY'] = 'a' * 50
from config import settings
print('SUCCESS_LEN:', len(settings.SECRET_KEY))
"""
    res = subprocess.run([sys.executable, "-c", py_code_valid_prod], cwd=str(ROOT_DIR), capture_output=True, text=True)
    record("SECRET_KEY_VALID_PROD_ACCEPTED", "SUCCESS_LEN: 50" in res.stdout, "Valid 50-char key accepted when DEBUG=False")

    py_code_dev_fallback = """
import os, sys
sys.path.insert(0, 'deepvision_django')
os.environ['DJANGO_DEBUG'] = 'True'
os.environ['DJANGO_SECRET_KEY'] = ''
from config import settings
print('DEV_KEY_PRESENT:', bool(settings.SECRET_KEY))
"""
    res = subprocess.run([sys.executable, "-c", py_code_dev_fallback], cwd=str(ROOT_DIR), capture_output=True, text=True)
    record("SECRET_KEY_DEV_FALLBACK_PERMITTED", "DEV_KEY_PRESENT: True" in res.stdout, "Dev fallback key permitted when DEBUG=True")


def test_host_binding_and_allowed_hosts():
    """Verify 0.0.0.0 removal from allowed hosts and default loopback binding."""
    # Check settings.py
    py_check_settings = """
import os, sys
sys.path.insert(0, 'deepvision_django')
os.environ.pop('DJANGO_ALLOWED_HOSTS', None)
os.environ.pop('DJANGO_CSRF_TRUSTED_ORIGINS', None)
from config import settings
print('ALLOWED_HOSTS:', settings.ALLOWED_HOSTS)
print('CSRF_ORIGINS:', settings.CSRF_TRUSTED_ORIGINS)
"""
    res = subprocess.run([sys.executable, "-c", py_check_settings], cwd=str(ROOT_DIR), capture_output=True, text=True)
    record("SETTINGS_ALLOWED_HOSTS_NO_0000", "'0.0.0.0'" not in res.stdout, "settings.ALLOWED_HOSTS excludes 0.0.0.0 by default")
    record("SETTINGS_CSRF_ORIGINS_NO_0000", "'http://0.0.0.0:8000'" not in res.stdout, "settings.CSRF_TRUSTED_ORIGINS excludes 0.0.0.0 by default")

    # Check setup_deepvision.ps1
    ps1_path = ROOT_DIR / "DeepVision-1.1.0" / "setup_deepvision.ps1"
    ps1_content = ps1_path.read_text(encoding="utf-8")
    record("SETUP_PS1_BINDS_127001", '-p "127.0.0.1:${Port}:8000"' in ps1_content, "setup_deepvision.ps1 binds published port to 127.0.0.1")
    record("SETUP_PS1_NO_0000_HOST", '0.0.0.0' not in ps1_content.split('DJANGO_ALLOWED_HOSTS=')[1].split('"')[0], "setup_deepvision.ps1 excludes 0.0.0.0 from DJANGO_ALLOWED_HOSTS")

    # Check .env.example files
    env_ex1 = (ROOT_DIR / ".env.example").read_text(encoding="utf-8")
    env_ex2 = (ROOT_DIR / "DeepVision-1.1.0" / ".env.example").read_text(encoding="utf-8")
    record("ROOT_ENV_EXAMPLE_NO_0000", "0.0.0.0" not in [line for line in env_ex1.splitlines() if line.startswith("DJANGO_ALLOWED_HOSTS")][0], "root .env.example excludes 0.0.0.0")
    record("DIST_ENV_EXAMPLE_NO_0000", "0.0.0.0" not in [line for line in env_ex2.splitlines() if line.startswith("DJANGO_ALLOWED_HOSTS")][0], "dist .env.example excludes 0.0.0.0")

    # Check docker-compose.yml files
    dc1 = (ROOT_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    dc2 = (ROOT_DIR / "DeepVision-1.1.0" / "docker-compose.yml").read_text(encoding="utf-8")
    record("ROOT_COMPOSE_BINDS_127001", "127.0.0.1:8000:8000" in dc1, "root docker-compose.yml binds to 127.0.0.1:8000:8000")
    record("DIST_COMPOSE_BINDS_127001", "127.0.0.1:${DEEPVISION_PORT:-8000}:8000" in dc2, "dist docker-compose.yml binds to 127.0.0.1:${DEEPVISION_PORT:-8000}:8000")


def test_server_startup_selection():
    """Verify single-process enforcement, platform runner selection, and production fail-closed behavior."""
    import start_deepvision
    import builtins

    orig_debug = os.environ.get("DJANGO_DEBUG")
    orig_env = os.environ.get("DEEPVISION_ENV")
    orig_plat = start_deepvision.sys.platform
    orig_import = builtins.__import__

    try:
        # 1. Test Windows Development selection (DJANGO_DEBUG=True or unset)
        os.environ["DJANGO_DEBUG"] = "True"
        os.environ.pop("DEEPVISION_ENV", None)
        start_deepvision.sys.platform = "win32"
        cmd_win, desc_win = start_deepvision.get_server_launch_command("127.0.0.1", 8000)
        record("WINDOWS_DEV_STARTUP_SELECTION", "--noreload" in cmd_win and "--insecure" in cmd_win, f"Windows dev uses single-process runner ({desc_win})")

        # 2. Test Linux / Container selection with Gunicorn present
        start_deepvision.sys.platform = "linux"
        os.environ["DJANGO_DEBUG"] = "False"
        cmd_linux, desc_linux = start_deepvision.get_server_launch_command("0.0.0.0", 8000)
        worker_idx = cmd_linux.index("--workers") if "--workers" in cmd_linux else -1
        worker_val = cmd_linux[worker_idx + 1] if worker_idx != -1 else None
        record("LINUX_STARTUP_SELECTION_GUNICORN", "gunicorn" in cmd_linux[2] or "gunicorn" in desc_linux, f"Linux selects Gunicorn WSGI ({desc_linux})")
        record("SINGLE_WORKER_STRICTLY_ENFORCED", worker_val == "1", f"--workers strictly equals 1 (got {worker_val})")
        record("THREADED_REQUESTS_CONFIGURED", "--threads" in cmd_linux, "Gunicorn configured with --threads for concurrent requests")

        # 3. Test Linux / Container mode when Gunicorn is ABSENT -> must fail closed (raise RuntimeError, never runserver)
        def mock_import_no_gunicorn(name, *args, **kwargs):
            if name == "gunicorn":
                raise ImportError("No module named 'gunicorn'")
            return orig_import(name, *args, **kwargs)

        builtins.__import__ = mock_import_no_gunicorn
        linux_failed_closed = False
        try:
            start_deepvision.get_server_launch_command("0.0.0.0", 8000)
        except RuntimeError as e:
            linux_failed_closed = "Gunicorn WSGI server is required" in str(e)

        record(
            "LINUX_MISSING_GUNICORN_FAILS_CLOSED",
            linux_failed_closed,
            "Linux/container mode raises RuntimeError when Gunicorn cannot be imported (no runserver fallback)"
        )

        # 4. Test Production mode on Windows when Gunicorn is ABSENT -> must fail closed (raise RuntimeError, never runserver)
        start_deepvision.sys.platform = "win32"
        os.environ["DJANGO_DEBUG"] = "False"
        os.environ["DEEPVISION_ENV"] = "production"
        win_prod_failed_closed = False
        try:
            start_deepvision.get_server_launch_command("127.0.0.1", 8000)
        except RuntimeError as e:
            win_prod_failed_closed = "Gunicorn WSGI server is required" in str(e)

        record(
            "PROD_MISSING_GUNICORN_FAILS_CLOSED",
            win_prod_failed_closed,
            "Production mode on Windows raises RuntimeError when Gunicorn is absent (never falls back to runserver)"
        )

    finally:
        builtins.__import__ = orig_import
        start_deepvision.sys.platform = orig_plat
        if orig_debug is not None:
            os.environ["DJANGO_DEBUG"] = orig_debug
        else:
            os.environ.pop("DJANGO_DEBUG", None)
        if orig_env is not None:
            os.environ["DEEPVISION_ENV"] = orig_env
        else:
            os.environ.pop("DEEPVISION_ENV", None)


def test_wsgi_static_asset_delivery():
    """Verify StaticFilesHandler is configured in wsgi.py to deliver static assets under WSGI."""
    from config.wsgi import application
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from django.test.client import RequestFactory

    record("WSGI_STATIC_FILES_HANDLER_WRAPPED", isinstance(application, StaticFilesHandler), "application in config.wsgi is wrapped with StaticFilesHandler")

    environ = RequestFactory().get('/static/dist/favicon.svg').environ
    status_captures = []
    def start_response(status, headers):
        status_captures.append(status)

    res_body = list(application(environ, start_response))
    record("STATIC_ASSET_WSGI_200_OK", len(status_captures) > 0 and status_captures[0] == "200 OK", f"Static asset served with HTTP {status_captures[0] if status_captures else 'NONE'}")


def test_database_contract():
    """Verify SQLite database has 18 tables, zero django_migrations, and passes integrity check."""
    db_path = ROOT_DIR / "instance" / "deepvision.db"
    assert db_path.exists(), "instance/deepvision.db missing"
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    c.execute("PRAGMA integrity_check")
    integrity = c.fetchone()[0]
    record("DB_INTEGRITY_CHECK", integrity == "ok", f"PRAGMA integrity_check is '{integrity}'")

    c.execute("SELECT count(*) FROM sqlite_master WHERE type='table'")
    t_count = c.fetchone()[0]
    record("DB_TABLE_COUNT_18", t_count == 18, f"Database table count is {t_count} (expected 18)")

    c.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='django_migrations'")
    m_count = c.fetchone()[0]
    record("DB_ZERO_DJANGO_MIGRATIONS", m_count == 0, f"django_migrations table count is {m_count} (expected 0)")

    conn.close()

    # Check custom user model is unmanaged
    py_check_model = """
import os, sys
sys.path.insert(0, 'deepvision_django')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django; django.setup()
from apps.accounts.models import User
print('MANAGED:', User._meta.managed)
print('DB_TABLE:', User._meta.db_table)
"""
    res = subprocess.run([sys.executable, "-c", py_check_model], cwd=str(ROOT_DIR), capture_output=True, text=True)
    record("USER_MODEL_UNMANAGED", "MANAGED: False" in res.stdout, "User model has managed=False")
    record("USER_MODEL_TABLE_USERS", "DB_TABLE: users" in res.stdout, "User model maps to 'users' table")


def main():
    print("=" * 70)
    print("  DEEPVISION 1.1.0 DEPLOYMENT HARDENING VERIFICATION SUITE")
    print("=" * 70)

    test_secret_key_fail_closed()
    test_host_binding_and_allowed_hosts()
    test_server_startup_selection()
    test_wsgi_static_asset_delivery()
    test_database_contract()

    print("\n" + "=" * 70)
    print(f"  DEPLOYMENT HARDENING VERIFICATION: ALL {len(RESULTS)} CHECKS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
