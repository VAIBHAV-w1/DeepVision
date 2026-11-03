# DEEPVISION 4.0 — ARCHITECTURAL RESTRUCTURING IMPLEMENTATION PLAN

**Target:** Complete End-to-End Functional Surveillance Platform  
**Execution Order:** Autonomous Phased Loop  

---

## 1. PHASE SUMMARY & EXECUTION SEQUENCE

```mermaid
flowchart TD
    P1["Phase 1: Project Audit<br/>(docs/PROJECT_AUDIT.md)"] --> P2["Phase 2: PRD & Architecture<br/>(PRD.md & docs/*)"]
    P2 --> P3["Phase 3 & 4: Backend & DB<br/>Verify Endpoints & DB Integrity"]
    P3 --> P5["Phase 5: Frontend Restructuring<br/>Rebuild 10 Canonical Pages"]
    P5 --> P6["Phase 6: Live Camera & Streaming<br/>Clear Video & Interactive Zone Canvas"]
    P6 --> P7["Phase 7, 8, 9: AI Engine<br/>YOLO11n + ByteTrack + Anomaly"]
    P7 --> P10["Phase 10: Webcam 0 Demo<br/>Physical Intrusion Verification"]
    P10 --> P11["Phase 11 & 12: Workflows & UI<br/>Linear/shadcn Design & Auth"]
    P11 --> P15["Phase 15 & 16: Testing & Verification<br/>CDP Screenshots & Regression Suites"]
    P15 --> P20["Phase 20: Delivery Reports<br/>Final Verification Reports"]
```

---

## 2. KEY REFACTORING TASKS

### Task 1: Rebuild Independent `Cameras.jsx` Page
- Extract full camera management from `Surveillance.jsx`.
- Implement camera inventory table, hardware status indicators, add/edit/delete modals, test connection button, and direct link to live monitoring.
- Ensure `Cameras.jsx` is NOT an alias, but a full-featured top-level page component.

### Task 2: Disband `SecurityCenter.jsx` and Direct-Wire Canonical Pages
- Eliminate `SecurityCenter.jsx` wrapper.
- Wire each route directly to its independent component in `App.jsx`:
  - `#/alerts` -> `Alerts.jsx`
  - `#/recordings` -> `Recordings.jsx`
  - `#/evidence` -> `Evidence.jsx`
  - `#/cases` -> `Cases.jsx`
  - `#/notifications` -> `Notifications.jsx`
- Update `Navbar.jsx` nav items to target their individual pages directly without synthetic sub-tabs.

### Task 3: Ensure Clean Route Routing in `App.jsx`
- Update `parseRoute()` to parse direct paths (`/cameras/`, `/alerts/`, etc.) and hash routes (`#/cameras`, `#/alerts`, etc.) without redirecting to tabbed wrappers.
- Provide clean unmount cleanup on all stream player components.

### Task 4: Automated Build & Verification Loop
- Run `npm run build` in `frontend/` to produce the production bundle in `deepvision_django/static/dist/`.
- Verify using Node.js CDP browser tests on all 7 viewports.
- Capture high-resolution authenticated screenshots of all 10 pages.
- Execute full regression test suites.

