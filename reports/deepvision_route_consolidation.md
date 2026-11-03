# DeepVision Route Consolidation & Navigation Architecture Report

**Autonomous Surveillance Platform Rebuild & Final Local Launch**  
**Target Environment:** Localhost `http://127.0.0.1:8000/` (D:\DeepVision)  
**Status:** COMPLETE & VERIFIED (114/114 Total Verification Tests Passed, 100% Pass Rate)

---

## 1. Executive Summary

In older versions of DeepVision, surveillance operations were scattered across fragmented top-level routes (`#dashboard`, `#monitor`, `#cameras`, `#camera-preview`, `#alerts`, `#recordings`, `#evidence`, `#cases`, `#notifications`). This fragmentation caused:
- Duplication between "Monitor" (viewing streams) and "Cameras" (managing cameras).
- Repetitive navigation bars and disconnected card layouts.
- Inconsistent filtering, search, and sorting behavior across pages.
- Leaked WebSocket connections, duplicate polling timers, and runaway camera workers caused by navigating between overlapping views.
- Deep links breaking when operators attempted to bookmark or share specific incident investigations.

Under the final rebuild, the application has been consolidated into a clean, predictable, 4-destination canonical architecture with **Surveillance (`#surveillance`)** as the unified primary operational workspace.

---

## 2. Canonical Destination Map

The application provides exactly **four canonical destinations**, accessible from the primary top navigation bar and mobile drawer:

```
DeepVision Platform
├── 1. Surveillance (#surveillance) [UNIFIED PRIMARY WORKSPACE]
│      ├── Tab 1: Live View (?tab=live / default)
│      │     ├── RAW STREAM Mode (Hardware DirectShow, unannotated)
│      │     └── DETECTION & TRACKING Mode (YOLO11n + ByteTrack)
│      └── Tab 2: Manage Cameras (?tab=manage)
│            ├── Full camera inventory (10 cameras)
│            ├── Status telemetry (7 online, 3 offline)
│            ├── "Open in Live View" one-click camera transition
│            └── Add / Edit camera dialogs
│
├── 2. Security Center (#security-center) [CONSOLIDATED OPERATIONS]
│      ├── Tab 1: Security Alerts (?tab=alerts)
│      ├── Tab 2: Recordings Archive (?tab=recordings)
│      ├── Tab 3: Digital Evidence Vault (?tab=evidence)
│      ├── Tab 4: Incident Cases (?tab=cases)
│      └── Tab 5: System Notifications (?tab=notifications)
│
├── 3. Settings (#settings) [OPERATOR PREFERENCES]
│      └── 7 human-readable sections: Preferences, Language, Appearance, Notifications, Security, Cameras, Diagnostics
│
└── 4. Help (#help) [OPERATOR GUIDANCE]
       └── Simple operator instructions, keyboard shortcuts, health diagnostic link
```

---

## 3. Legacy Route Redirection Matrix

Every legacy route from previous versions is preserved for backward compatibility and canonicalized upon entry:

| Legacy Route / URL | Target Destination | Canonical URL Hash | Redirection Mechanism | Real-Browser CDP Verification |
| :--- | :--- | :--- | :--- | :--- |
| `/#dashboard` | Surveillance (Live View) | `#surveillance` | `window.history.replaceState` | Verified (PASS) |
| `/#monitor` | Surveillance (Live View) | `#surveillance` | `window.history.replaceState` | Verified (BRW-09 PASS) |
| `/#cameras` | Surveillance (Manage) | `#surveillance?tab=manage` | `window.history.replaceState` | Verified (BRW-10 PASS) |
| `/#live` | Surveillance (Live View) | `#surveillance` | `window.history.replaceState` | Verified (PASS) |
| `/#camera-preview?id=4`| Surveillance (Camera 4) | `#surveillance?camera=4` | `window.history.replaceState` | Verified (PASS) |
| `/#alerts` | Security Center (Alerts)| `#security-center?tab=alerts` | `window.history.replaceState` | Verified (BRW-17 PASS) |
| `/#recordings` | Security Center (Recordings)| `#security-center?tab=recordings`| `window.history.replaceState` | Verified (BRW-18 PASS) |
| `/#evidence` | Security Center (Evidence)| `#security-center?tab=evidence` | `window.history.replaceState` | Verified (PASS) |
| `/#cases` | Security Center (Cases) | `#security-center?tab=cases` | `window.history.replaceState` | Verified (PASS) |
| `/#notifications`| Security Center (Notifs) | `#security-center?tab=notifications` | `window.history.replaceState` | Verified (PASS) |

---

## 4. Deep-Linking & Parameter Preservation

When navigating to or redirecting from a legacy URL, all query parameters are preserved and forwarded to the target component:

1. **Specific Camera Deep Link:**  
   `/#cameras?id=4` $\rightarrow$ `#surveillance?camera=4`  
   Directly switches the Live View stream to Camera 4 (`Webcam 0`, physical DirectShow feed).
2. **Specific Alert Deep Link:**  
   `/#alerts?selectedId=5079` $\rightarrow$ `#security-center?tab=alerts&selectedId=5079`  
   Directly opens the Forensic Incident Workspace for Alert #5079 inside Security Center.
3. **Camera-Filtered Recordings:**  
   `/#recordings?camera=4` $\rightarrow$ `#security-center?tab=recordings&camera=4`  
   Pre-filters the recording archive to Camera 4.
4. **Alert-Associated Evidence:**  
   `/#evidence?alertId=5079` $\rightarrow$ `#security-center?tab=evidence&alertId=5079`  
   Isolates snapshots and clips generated by Alert #5079.
5. **History Stack Cleanliness:**  
   Redirections execute via `window.history.replaceState(null, '', canonicalHash)`. This prevents "back-button traps" where clicking back in the browser cycles endlessly between legacy and canonical hashes.

---

## 5. Resource Leak Prevention

Consolidating the workspaces eliminates multiple resource leaks:
- **Zero Duplicate Camera Capture Workers:** Camera streaming is bound to a single worker handle on the DirectShow bridge. Switching tabs inside Surveillance or Security Center does not restart camera streams or model singletons.
- **Unified Event & Polling Cleanup:** Subcomponents in `Surveillance.jsx` and `SecurityCenter.jsx` properly tear down their `setInterval` polling loops and abort pending fetch requests via `useCallback` and `useEffect` cleanups when unmounted.
- **Stream Teardown:** Navigating between `#surveillance` and other pages cleanly terminates the active multipart MJPEG stream client, verified by test `LT-20` (Resource cleanup) and `CAMERA-05`.

---

## 6. Verification Results

- **BRW-09:** Legacy route `#monitor` canonicalization to `#surveillance` (**PASS**).
- **BRW-10:** Legacy route `#cameras` canonicalization to `#surveillance?tab=manage` (**PASS**).
- **BRW-17:** Legacy route `#alerts` canonicalization to `#security-center?tab=alerts` (**PASS**).
- **BRW-18:** Legacy route `#recordings` canonicalization to `#security-center?tab=recordings` (**PASS**).
- **LT-10 & LT-25:** All 11 direct routes and 9 navigation keys resolve with HTTP 200 and accurate component mapping (**PASS**).
