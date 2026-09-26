# DeepVision Phase 14 — Cleanup Manifest
======================================

Date: 2026-09-25
Objective: Complete Elimination of Flask Runtime & Obsolete Artifacts

| Deleted Path | Reason | References Checked | Replacement, If Any |
| :--- | :--- | :--- | :--- |
| `d:\DeepVision\app\` | Legacy Flask application directory (app factory, blueprints, routes, templates, Flask models, services, Flask config). | Searched all active imports in `deepvision_django`, `config`, and root scripts. Verified zero runtime references remaining. | Native Django application apps: `apps.core`, `apps.accounts`, `apps.cameras`, `apps.recordings`, `apps.evidence`, `apps.alerts`, `apps.notifications`, and `apps.surveillance`. |
| `d:\DeepVision\run.py` | Legacy Flask standalone web server entrypoint (`app.run(port=5000)`). | Verified launcher and services. No active processes or scripts invoke `run.py`. | `deepvision_django/manage.py` and `start_deepvision.py`. |
| `d:\DeepVision\supervisor.py` | Dual-process Flask supervisor daemon that launched Flask on port 5000. | Checked startup scripts and background task manifests. | Single-process native Django architecture launched via `start_deepvision.py`. |
| `d:\DeepVision\tests\` | Legacy Flask test suite relying on Flask `create_app()` and Flask test client. | Verified no Django tests or verification suites depend on `tests/`. | `deepvision_django/verify_phase14_django_native.py`. |
| `d:\DeepVision\test_matrix.py` | Legacy Flask test matrix runner testing retired Flask routes. | No external references or automation dependencies. | `deepvision_django/verify_phase14_django_native.py`. |
| `d:\DeepVision\verify_phase_a.py` | Historical Phase A verification script targeting Flask camera/AI layer. | No references in active runtime. | Historical verification passed; archived in `backups/pre_cleanup_archive/`. |
| `d:\DeepVision\verify_phase_b.py` | Historical Phase B verification script targeting Flask camera registry. | No references in active runtime. | Historical verification passed; archived in `backups/pre_cleanup_archive/`. |
| `d:\DeepVision\tmp_h264.mp4` | Temporary codec diagnostic video artifact. | Scratch media artifact; no references. | None (scratch artifact). |
| `d:\DeepVision\tmp_mp4v.mp4` | Temporary codec diagnostic video artifact. | Scratch media artifact; no references. | None (scratch artifact). |
| `d:\DeepVision\tmp_test.html` | Temporary HTML testing snippet. | Scratch artifact; no references. | None (scratch artifact). |

## Packages Removed from Dependencies
- `Flask` (uninstalled from virtual environment, removed from `requirements.txt`)
- `Flask-SQLAlchemy` (uninstalled from virtual environment, removed from `requirements.txt`)

## Pre-Cleanup Backup
All deleted files were preserved in:
`d:\DeepVision\backups\pre_cleanup_archive\`
