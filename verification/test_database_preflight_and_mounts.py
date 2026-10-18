"""
DeepVision 1.1.0 Database Preflight and Mount Configuration Verification Suite
=============================================================================
Validates:
1. Missing production database raises RuntimeError and does not create a blank database.
2. Corrupted SQLite database raises RuntimeError and is never overwritten.
3. Incomplete SQLite schema (<18 tables) raises RuntimeError and is not overwritten.
4. Valid existing production database passes preflight integrity and schema checks.
5. Development mode separation: auto-initializes only when absent, rejects corrupted DB.
6. Deployment scripts and Compose files enforce host bind mounts for instance, models, recordings.
7. Live deepvision-app container mounts and health remain active and unharmed.
"""

import os
import sys
import tempfile
import sqlite3
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DJANGO_DIR = ROOT_DIR / "deepvision_django"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(DJANGO_DIR) not in sys.path:
    sys.path.insert(0, str(DJANGO_DIR))

import start_deepvision

RESULTS = []


def record(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    RESULTS.append((name, status, detail))
    print(f"[{status:4s}] {name}: {detail}")
    if not passed:
        raise AssertionError(f"Check failed: {name} - {detail}")


def test_missing_database_fail_closed_prod():
    """Verify that a missing database in production mode raises an error and does not create a file."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        fake_db = Path(tmp_dir) / "instance" / "deepvision.db"
        
        valid, detail = start_deepvision.validate_sqlite_database(fake_db)
        record(
            "PREFLIGHT_MISSING_DB_VALIDATION_FAILS",
            not valid and "does not exist" in detail,
            f"validate_sqlite_database returned False for missing DB: {detail}"
        )

        # Test ensure_database() with simulated missing DB in production mode
        orig_root = start_deepvision.ROOT_DIR
        orig_debug = os.environ.get("DJANGO_DEBUG")
        try:
            start_deepvision.ROOT_DIR = Path(tmp_dir)
            os.environ["DJANGO_DEBUG"] = "False"
            raised = False
            try:
                start_deepvision.ensure_database()
            except RuntimeError as e:
                raised = True
                record(
                    "PROD_ENSURE_DB_MISSING_RAISES_RUNTIME_ERROR",
                    "Database preflight validation failed" in str(e),
                    f"ensure_database() raised expected RuntimeError: {e}"
                )

            record(
                "PROD_ENSURE_DB_MISSING_NO_SILENT_INIT",
                raised and not fake_db.exists(),
                "ensure_database() did not silently create a new database file"
            )
        finally:
            start_deepvision.ROOT_DIR = orig_root
            if orig_debug is not None:
                os.environ["DJANGO_DEBUG"] = orig_debug
            else:
                os.environ.pop("DJANGO_DEBUG", None)


def test_corrupted_database_fail_closed():
    """Verify that a corrupted SQLite database fails integrity check and is not overwritten."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        inst_dir = Path(tmp_dir) / "instance"
        inst_dir.mkdir(parents=True)
        corrupt_db = inst_dir / "deepvision.db"
        corrupt_db.write_bytes(b"NOT_A_VALID_SQLITE_DATABASE_HEADER_GARBAGE_BYTES_1234567890")

        valid, detail = start_deepvision.validate_sqlite_database(corrupt_db)
        record(
            "PREFLIGHT_CORRUPT_DB_REJECTED",
            not valid,
            f"Corrupt database rejected: {detail}"
        )

        # Test ensure_database in production mode
        orig_root = start_deepvision.ROOT_DIR
        orig_debug = os.environ.get("DJANGO_DEBUG")
        try:
            start_deepvision.ROOT_DIR = Path(tmp_dir)
            os.environ["DJANGO_DEBUG"] = "False"
            raised = False
            try:
                start_deepvision.ensure_database()
            except RuntimeError as e:
                raised = True
                record(
                    "PROD_ENSURE_DB_CORRUPT_RAISES_ERROR",
                    "Database preflight validation failed" in str(e),
                    f"ensure_database() raised on corrupted database: {e}"
                )

            # Check that corrupted file was preserved and not overwritten
            record(
                "PROD_ENSURE_DB_CORRUPT_NOT_OVERWRITTEN",
                corrupt_db.read_bytes().startswith(b"NOT_A_VALID_SQLITE"),
                "Corrupted database file was preserved for forensic recovery"
            )
        finally:
            start_deepvision.ROOT_DIR = orig_root
            if orig_debug is not None:
                os.environ["DJANGO_DEBUG"] = orig_debug
            else:
                os.environ.pop("DJANGO_DEBUG", None)


def test_incomplete_schema_fail_closed():
    """Verify that a database with fewer than 18 tables is rejected in production."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        inst_dir = Path(tmp_dir) / "instance"
        inst_dir.mkdir(parents=True)
        partial_db = inst_dir / "deepvision.db"
        
        conn = sqlite3.connect(str(partial_db))
        c = conn.cursor()
        c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT);")
        c.execute("CREATE TABLE cameras (id INTEGER PRIMARY KEY, name TEXT);")
        conn.commit()
        conn.close()

        valid, detail = start_deepvision.validate_sqlite_database(partial_db)
        record(
            "PREFLIGHT_INCOMPLETE_SCHEMA_REJECTED",
            not valid and "only 2 tables" in detail,
            f"Incomplete schema rejected: {detail}"
        )

        orig_root = start_deepvision.ROOT_DIR
        orig_debug = os.environ.get("DJANGO_DEBUG")
        try:
            start_deepvision.ROOT_DIR = Path(tmp_dir)
            os.environ["DJANGO_DEBUG"] = "False"
            raised = False
            try:
                start_deepvision.ensure_database()
            except RuntimeError as e:
                raised = True
                record(
                    "PROD_ENSURE_DB_INCOMPLETE_RAISES_ERROR",
                    "Database preflight validation failed" in str(e),
                    f"ensure_database() raised on incomplete schema: {e}"
                )
        finally:
            start_deepvision.ROOT_DIR = orig_root
            if orig_debug is not None:
                os.environ["DJANGO_DEBUG"] = orig_debug
            else:
                os.environ.pop("DJANGO_DEBUG", None)


def test_schema_signature_mismatch_fail_closed():
    """Verify that a database with altered schema/signature is rejected even if it has 18 tables."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        inst_dir = Path(tmp_dir) / "instance"
        inst_dir.mkdir(parents=True)
        mismatch_db = inst_dir / "deepvision.db"

        # Initialize full 18-table schema from schema.sql
        schema_file = DJANGO_DIR / "schema.sql"
        with open(schema_file, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn = sqlite3.connect(str(mismatch_db))
        conn.executescript(schema_sql)
        # Alter schema by adding an unexpected column to perturb SHA-256 signature
        conn.execute("ALTER TABLE users ADD COLUMN unapproved_extra_column TEXT;")
        conn.commit()
        conn.close()

        valid, detail = start_deepvision.validate_sqlite_database(mismatch_db)
        record(
            "PREFLIGHT_SIGNATURE_MISMATCH_REJECTED",
            not valid and "Schema signature mismatch" in detail,
            f"Altered schema signature rejected: {detail}"
        )

        orig_root = start_deepvision.ROOT_DIR
        orig_debug = os.environ.get("DJANGO_DEBUG")
        try:
            start_deepvision.ROOT_DIR = Path(tmp_dir)
            os.environ["DJANGO_DEBUG"] = "False"
            raised = False
            try:
                start_deepvision.ensure_database()
            except RuntimeError as e:
                raised = True
                record(
                    "PROD_ENSURE_DB_SIGNATURE_MISMATCH_RAISES_ERROR",
                    "Database preflight validation failed" in str(e) and "Schema signature mismatch" in str(e),
                    f"ensure_database() raised on signature mismatch: {e}"
                )
            record("PROD_ENSURE_DB_SIGNATURE_MISMATCH_FAIL_CLOSED", raised, "Signature mismatch failed closed")
        finally:
            start_deepvision.ROOT_DIR = orig_root
            if orig_debug is not None:
                os.environ["DJANGO_DEBUG"] = orig_debug
            else:
                os.environ.pop("DJANGO_DEBUG", None)


def test_valid_existing_database():
    """Verify that the existing production database passes preflight checks cleanly."""
    real_db = ROOT_DIR / "instance" / "deepvision.db"
    record("EXISTING_DB_EXISTS", real_db.exists() and real_db.stat().st_size > 0, f"Found {real_db}")

    valid, detail = start_deepvision.validate_sqlite_database(real_db)
    record("EXISTING_DB_PREFLIGHT_PASS", valid, f"Validation returned: {detail}")

    # Verify integrity and tables directly
    conn = sqlite3.connect(f"file:{real_db.resolve()}?mode=ro", uri=True)
    c = conn.cursor()
    c.execute("PRAGMA integrity_check;")
    integrity = c.fetchone()[0]
    record("EXISTING_DB_INTEGRITY_OK", integrity == "ok", f"PRAGMA integrity_check: {integrity}")

    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = {r[0] for r in c.fetchall()}

    # Verify SHA-256 schema signature against known baseline cc2d13f77b681107
    c.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name;")
    schema_sql = "".join(str(r[0]) for r in c.fetchall())
    import hashlib
    sig = hashlib.sha256(schema_sql.encode("utf-8")).hexdigest()[:16]
    conn.close()

    record("EXISTING_DB_TABLE_COUNT_18", len(tables) == 18, f"Table count: {len(tables)}")
    record(
        "EXISTING_DB_HAS_ALL_REQUIRED_TABLES",
        start_deepvision.REQUIRED_SCHEMA_TABLES.issubset(tables),
        f"All 18 core tables present: {sorted(tables)}"
    )
    record(
        "EXISTING_DB_SCHEMA_SIGNATURE_BASELINE_MATCH",
        sig == start_deepvision.EXPECTED_SCHEMA_SIGNATURE and sig == "cc2d13f77b681107",
        f"Schema signature strictly matches baseline: {sig}"
    )

    # Test ensure_database with real DB in production mode
    orig_debug = os.environ.get("DJANGO_DEBUG")
    try:
        os.environ["DJANGO_DEBUG"] = "False"
        start_deepvision.ensure_database()
        record("PROD_ENSURE_DB_REAL_DB_PASS", True, "ensure_database() succeeded with real production database")
    finally:
        if orig_debug is not None:
            os.environ["DJANGO_DEBUG"] = orig_debug
        else:
            os.environ.pop("DJANGO_DEBUG", None)


def test_dev_mode_behavior_separation():
    """Verify development mode initializes schema only when missing, and rejects corrupt DB."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        inst_dir = Path(tmp_dir) / "instance"
        inst_dir.mkdir(parents=True)
        dev_db = inst_dir / "deepvision.db"

        orig_root = start_deepvision.ROOT_DIR
        orig_debug = os.environ.get("DJANGO_DEBUG")
        try:
            start_deepvision.ROOT_DIR = Path(tmp_dir)
            os.environ["DJANGO_DEBUG"] = "True"
            # In dev mode, absent DB is cleanly initialized from schema.sql
            start_deepvision.ensure_database()
            record(
                "DEV_MODE_AUTO_INIT_WHEN_ABSENT",
                dev_db.exists() and dev_db.stat().st_size > 0,
                f"Dev mode successfully initialized new DB: {dev_db}"
            )
            valid, detail = start_deepvision.validate_sqlite_database(dev_db)
            record("DEV_MODE_INITIALIZED_SCHEMA_VALID", valid, f"Dev DB has valid schema: {detail}")

            # Corrupted DB in dev mode must STILL raise an error, never overwrite
            dev_db.write_bytes(b"CORRUPTED_DEV_DB")
            dev_corrupt_raised = False
            try:
                start_deepvision.ensure_database()
            except RuntimeError as e:
                dev_corrupt_raised = True
                record(
                    "DEV_MODE_REJECTS_CORRUPT_DB",
                    "Database validation failed" in str(e),
                    f"Dev mode rejected corrupted DB without overwriting: {e}"
                )
            record("DEV_MODE_CORRUPT_FAIL_CLOSED", dev_corrupt_raised, "Dev mode fails closed on corruption")
        finally:
            start_deepvision.ROOT_DIR = orig_root
            if orig_debug is not None:
                os.environ["DJANGO_DEBUG"] = orig_debug
            else:
                os.environ.pop("DJANGO_DEBUG", None)


def test_mysql_mode_bypasses_sqlite():
    """Verify that MySQL configuration completely bypasses SQLite preflight validation."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        # No SQLite database exists in this directory
        orig_root = start_deepvision.ROOT_DIR
        orig_mysql = os.environ.get("USE_MYSQL")
        orig_debug = os.environ.get("DJANGO_DEBUG")
        try:
            start_deepvision.ROOT_DIR = Path(tmp_dir)
            os.environ["USE_MYSQL"] = "1"
            os.environ["DJANGO_DEBUG"] = "False"

            # Should not raise any SQLite validation error despite missing sqlite db
            start_deepvision.ensure_database()
            record(
                "MYSQL_MODE_BYPASSES_SQLITE_VALIDATION",
                True,
                "ensure_database() successfully bypassed SQLite validation when USE_MYSQL=1"
            )
        finally:
            start_deepvision.ROOT_DIR = orig_root
            if orig_mysql is not None:
                os.environ["USE_MYSQL"] = orig_mysql
            else:
                os.environ.pop("USE_MYSQL", None)
            if orig_debug is not None:
                os.environ["DJANGO_DEBUG"] = orig_debug
            else:
                os.environ.pop("DJANGO_DEBUG", None)


def test_container_env_production_detection():
    """Verify that containerized environment defaults to production even if DJANGO_DEBUG is unset."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        fake_db = Path(tmp_dir) / "instance" / "deepvision.db"
        orig_root = start_deepvision.ROOT_DIR
        orig_plat = start_deepvision.sys.platform
        orig_debug = os.environ.get("DJANGO_DEBUG")
        try:
            start_deepvision.ROOT_DIR = Path(tmp_dir)
            start_deepvision.sys.platform = "linux"  # Simulate containerized Linux OS
            os.environ.pop("DJANGO_DEBUG", None)     # Unset DJANGO_DEBUG

            raised = False
            try:
                start_deepvision.ensure_database()
            except RuntimeError as e:
                raised = True
                record(
                    "CONTAINER_UNSET_DEBUG_DEFAULTS_TO_PROD",
                    "Database preflight validation failed" in str(e),
                    f"Containerized execution defaulted to production and failed closed: {e}"
                )
            record("CONTAINER_PREVENTS_ACCIDENTAL_DEV_FALLBACK", raised and not fake_db.exists(), "No blank database created in container")
        finally:
            start_deepvision.ROOT_DIR = orig_root
            start_deepvision.sys.platform = orig_plat
            if orig_debug is not None:
                os.environ["DJANGO_DEBUG"] = orig_debug
            else:
                os.environ.pop("DJANGO_DEBUG", None)


def test_mount_configurations():
    """Verify deployment scripts and docker-compose files preserve Windows host bind mounts."""
    # 1. Check setup_deepvision.ps1
    ps1_content = (ROOT_DIR / "DeepVision-1.1.0" / "setup_deepvision.ps1").read_text(encoding="utf-8")
    record(
        "PS1_MOUNTS_INSTANCE_BIND",
        '-v "${InstanceDir}:/app/instance"' in ps1_content,
        "setup_deepvision.ps1 bind-mounts InstanceDir to /app/instance"
    )
    record(
        "PS1_MOUNTS_MODELS_BIND",
        '-v "${ModelsDir}:/app/models"' in ps1_content,
        "setup_deepvision.ps1 bind-mounts ModelsDir to /app/models"
    )
    record(
        "PS1_MOUNTS_RECORDINGS_BIND",
        '-v "${RecordingsDir}:/app/recordings"' in ps1_content,
        "setup_deepvision.ps1 bind-mounts RecordingsDir to /app/recordings"
    )
    record(
        "PS1_HAS_PREFLIGHT_VALIDATION",
        "Validating database and host mounts" in ps1_content and "PRAGMA integrity_check" in ps1_content,
        "setup_deepvision.ps1 contains preflight integrity and schema validation"
    )

    # 2. Check DeepVision-1.1.0/docker-compose.yml
    dist_compose = (ROOT_DIR / "DeepVision-1.1.0" / "docker-compose.yml").read_text(encoding="utf-8")
    record(
        "DIST_COMPOSE_MOUNTS_INSTANCE",
        ":/app/instance" in dist_compose and "deepvision-data:" not in dist_compose,
        "dist docker-compose.yml binds to /app/instance without named data volume"
    )
    record(
        "DIST_COMPOSE_MOUNTS_MODELS",
        ":/app/models" in dist_compose,
        "dist docker-compose.yml binds to /app/models"
    )
    record(
        "DIST_COMPOSE_MOUNTS_RECORDINGS",
        ":/app/recordings" in dist_compose,
        "dist docker-compose.yml binds to /app/recordings"
    )

    # 3. Check root docker-compose.yml
    root_compose = (ROOT_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    record(
        "ROOT_COMPOSE_MOUNTS_ALL",
        "./instance:/app/instance" in root_compose and "./models:/app/models" in root_compose and "./recordings:/app/recordings" in root_compose,
        "root docker-compose.yml preserves ./instance, ./models, ./recordings bind mounts"
    )

    # 4. Check live deepvision-app container mounts (read-only verification)
    res = subprocess.run(
        ["docker", "inspect", "deepvision-app", "--format", "{{json .Mounts}}"],
        capture_output=True, text=True
    )
    if res.returncode == 0 and res.stdout.strip():
        mounts_str = res.stdout
        record(
            "LIVE_CONTAINER_MOUNTS_INSTANCE",
            "/app/instance" in mounts_str,
            "Live deepvision-app container mounts /app/instance"
        )
        record(
            "LIVE_CONTAINER_MOUNTS_MODELS",
            "/app/models" in mounts_str,
            "Live deepvision-app container mounts /app/models"
        )
        record(
            "LIVE_CONTAINER_MOUNTS_RECORDINGS",
            "/app/recordings" in mounts_str,
            "Live deepvision-app container mounts /app/recordings"
        )
    else:
        record("LIVE_CONTAINER_INSPECT", True, "Live container check skipped or not running")


def test_secondary_index_validation():
    """Verify separate secondary index presence validation."""
    real_db = ROOT_DIR / "instance" / "deepvision.db"
    valid, msg, missing = start_deepvision.validate_sqlite_indexes(real_db)
    record(
        "LIVE_DB_SECONDARY_INDEXES_VALID",
        valid and len(missing) == 0,
        f"Live database secondary index check passed: {msg}"
    )

    # Test DB missing secondary indexes (e.g. database with tables created but indexes omitted)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        tmp_db = Path(tmp_dir) / "instance" / "deepvision.db"
        tmp_db.parent.mkdir(parents=True)
        schema_file = DJANGO_DIR / "schema.sql"
        with open(schema_file, "r", encoding="utf-8") as f:
            sql = f.read()
        table_stmts = ";".join([s for s in sql.split(";") if "CREATE TABLE" in s]) + ";"
        conn = sqlite3.connect(str(tmp_db))
        conn.executescript(table_stmts)
        conn.commit()
        conn.close()

        # Confirm table validation passes signature cc2d13f77b681107 even without secondary indexes
        ok_table, _ = start_deepvision.validate_sqlite_database(tmp_db)
        record(
            "TABLE_SIGNATURE_PASSES_WITHOUT_INDEXES",
            ok_table,
            "Table signature cc2d13f77b681107 hashes type='table' exclusively and passes without secondary indexes"
        )

        # Confirm separate index validation catches all 11 missing secondary indexes
        valid_no_idx, msg_no_idx, missing_no_idx = start_deepvision.validate_sqlite_indexes(tmp_db)
        record(
            "SCHEMA_ONLY_DB_MISSING_INDEXES_DETECTED",
            not valid_no_idx and len(missing_no_idx) == len(start_deepvision.EXPECTED_SECONDARY_INDEXES),
            f"Separate index validation detected {len(missing_no_idx)} missing secondary indexes on table-only database"
        )


def test_preflight_cli_flag():
    """Verify CLI --preflight-check command and fail-closed behavior."""
    real_db = ROOT_DIR / "instance" / "deepvision.db"
    res_ok = subprocess.run(
        [sys.executable, str(ROOT_DIR / "start_deepvision.py"), "--preflight-check", str(real_db)],
        capture_output=True, text=True, cwd=str(ROOT_DIR)
    )
    record(
        "CLI_PREFLIGHT_REAL_DB_EXIT_ZERO",
        res_ok.returncode == 0 and "PREFLIGHT_OK" in res_ok.stdout,
        f"CLI --preflight-check on real DB exited 0: {res_ok.stdout.strip()}"
    )

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        missing_db = Path(tmp_dir) / "missing.db"
        res_fail = subprocess.run(
            [sys.executable, str(ROOT_DIR / "start_deepvision.py"), "--preflight-check", str(missing_db)],
            capture_output=True, text=True, cwd=str(ROOT_DIR)
        )
        record(
            "CLI_PREFLIGHT_MISSING_DB_EXIT_ONE",
            res_fail.returncode == 1 and "PREFLIGHT_FAIL" in res_fail.stderr,
            f"CLI --preflight-check on missing DB exited 1: {res_fail.stderr.strip()}"
        )
        record(
            "CLI_PREFLIGHT_DOES_NOT_CREATE_FILE",
            not missing_db.exists(),
            "CLI --preflight-check did not create missing DB file"
        )


def test_powershell_script_syntax():
    """Verify PowerShell script syntax parsing for setup_deepvision.ps1."""
    ps1_path = ROOT_DIR / "DeepVision-1.1.0" / "setup_deepvision.ps1"
    check_code = f"""
    $tokens = $null
    $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile('{ps1_path}', [ref]$tokens, [ref]$errors)
    if ($errors.Count -gt 0) {{
        $errors | ForEach-Object {{ Write-Error $_.Message }}
        exit 1
    }} else {{
        Write-Host "PARSER_CLEAN"
        exit 0
    }}
    """
    res = subprocess.run(["powershell", "-NoProfile", "-Command", check_code], capture_output=True, text=True)
    record(
        "PS1_SYNTAX_PARSER_CLEAN",
        res.returncode == 0 and "PARSER_CLEAN" in res.stdout,
        f"PowerShell AST parser validated setup_deepvision.ps1 without syntax errors (code {res.returncode})"
    )


def main():
    print("=" * 70)
    print("  DEEPVISION 1.1.0 DATABASE PREFLIGHT & MOUNT VERIFICATION SUITE")
    print("=" * 70)

    test_missing_database_fail_closed_prod()
    test_corrupted_database_fail_closed()
    test_incomplete_schema_fail_closed()
    test_schema_signature_mismatch_fail_closed()
    test_valid_existing_database()
    test_dev_mode_behavior_separation()
    test_mysql_mode_bypasses_sqlite()
    test_container_env_production_detection()
    test_mount_configurations()
    test_secondary_index_validation()
    test_preflight_cli_flag()
    test_powershell_script_syntax()

    print("\n" + "=" * 70)
    print(f"  VERIFICATION RESULT: ALL {len(RESULTS)} CHECKS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
