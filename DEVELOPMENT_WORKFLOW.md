# DeepVision Development & Release Workflow

This document defines the strict version control, testing, and release protocol for the DeepVision repository.

---

## Immutable Release Principle

> **Every verified DeepVision release is an immutable versioned snapshot.**
> Never rewrite history, never force-push, never overwrite a previous release tag, and never reuse a release version number.

---

## Semantic Versioning Rules

DeepVision strictly follows [Semantic Versioning 2.0.0](https://semver.org/):

$$\text{Format: } \mathbf{v\text{MAJOR}.\text{MINOR}.\text{PATCH}}$$

- **MAJOR** (`v2.0.0`): Breaking architectural, database schema, or public REST API changes.
- **MINOR** (`v1.1.0`): New backward-compatible surveillance features, analytics modes, or UI capabilities.
- **PATCH** (`v1.0.1`): Backward-compatible bug fixes, UI/CSS polish, security patches, or performance optimizations.

---

## Release Step-by-Step Workflow

Before initiating any release, execute this standardized 10-step protocol:

```text
1. Inspect Working Tree    →  git status (ensure clean state and intended changes)
2. Run Test Suite         →  python verification/verify_final_restructure.py
3. Inspect Git Diff        →  git diff (verify exact code modifications)
4. Secret & Safety Audit   →  Verify no .env, db.sqlite3, or runtime artifacts staged
5. Update Version Files    →  Update VERSION and append new section in CHANGELOG.md
6. Stage & Commit          →  git add <files> && git commit -m "release: vX.Y.Z - <summary>"
7. Create Annotated Tag    →  git tag -a vX.Y.Z -m "DeepVision vX.Y.Z: <summary>"
8. Push Main Branch        →  git push origin main
9. Push Version Tag        →  git push origin vX.Y.Z
10. Create GitHub Release  →  Create release on GitHub (via gh release create or web UI)
```

---

## Strict Prohibitions

1. **NEVER** use `git push --force` or `--force-with-lease` on published branches.
2. **NEVER** move, delete, or retag an existing version tag.
3. **NEVER** commit secrets, passwords, SMTP credentials, or real `.env` files.
4. **NEVER** commit runtime databases (`deepvision.db`, `db.sqlite3`, `*.sqlite3`).
5. **NEVER** commit live surveillance media (`recordings/*.mp4`, `evidence/*`).
6. **NEVER** commit temporary browser profiles or local cache directories.
7. **NEVER** commit `node_modules/` or Python `__pycache__/`.
