# DeepVision Design System Specification (design.md)

## 1. Color Palette & Operational Tokens

DeepVision uses a dark operational palette engineered for low eye fatigue in 24/7 security environments, accented with restrained emerald security indicators:

### Core Surfaces
- `--bg-canvas`: `#080c14` (Deep charcoal canvas)
- `--bg-surface`: `#0f172a` (Obsidian card surface)
- `--bg-surface-raised`: `#1e293b` (Raised container background)
- `--bg-surface-subtle`: `#131d31` (Subtle input background)
- `--bg-surface-hover`: `#1e293b` (Hover highlight)
- `--bg-surface-glass`: `rgba(15, 23, 42, 0.85)` (Frosted HUD overlay)

### Borders & Dividers
- `--border-color`: `rgba(255, 255, 255, 0.08)` (Subtle card border)
- `--border-subtle`: `rgba(255, 255, 255, 0.04)` (Interior divider)
- `--border-focus`: `#10b981` (Focus ring)

### Typography Colors
- `--text-main`: `#f8fafc` (Primary text, high contrast)
- `--text-secondary`: `#94a3b8` (Secondary metadata)
- `--text-muted`: `#64748b` (Disabled or placeholder text)

### Security Accent & Status Indicators
- `--color-primary`: `#10b981` (Emerald green accent)
- `--color-primary-hover`: `#059669` (Darker emerald hover)
- `--color-primary-active`: `#047857` (Active state)
- `--color-live`: `#10b981` (Live camera status)
- `--color-recording`: `#ef4444` (Pulsing recording indicator)
- `--color-warn`: `#f59e0b` (Medium severity alert)
- `--color-critical`: `#dc2626` (Critical intrusion alert)

## 2. Typography
- **Display & Headings:** `Plus Jakarta Sans`, `Inter`, -apple-system, sans-serif.
- **Body & Controls:** `Inter`, -apple-system, sans-serif.
- **Telemetry & Monospace:** `JetBrains Mono`, monospace (used for timestamps, FPS, bitrates, IP addresses, track IDs).

## 3. Spacing & Radius Tokens
- `--radius-sm`: `8px`
- `--radius-md`: `12px`
- `--radius-lg`: `18px`
- `--radius-xl`: `24px` (Monitor bezels, auth cards)
- `--radius-full`: `9999px` (Telemetry pills, badges)

## 4. Component Rules
1. **Camera Monitor Container (Reference 1):**
   - 24px border radius, 2px border with subtle emerald/white tint, dark canvas backdrop.
   - Floating translucent telemetry HUD:
     - Top pill: Bitrate and FPS.
     - Top center: Camera name and zone.
     - Top right: Live digital clock.
     - Left bar: Vertical action buttons (alarm, spotlight, HD, AI toggle).
     - Right bar: Vertical control buttons (snapshot, record, mic, audio, fullscreen).
     - Bottom-left: 3-stage zoom control pill `[ - | 1X | + ]`.
     - Bottom-right: Circular frosted PTZ pad with digital panning support during zoom.
2. **Dashboard Overview:**
   - Multi-column grid: System health banner, metric cards, camera availability table, secondary compact live monitor, recent alerts list, recent recordings list.
   - Live camera preview is secondary (compact 16:9 thumbnail) to prevent dominating the dashboard.
3. **Table & Card Components:**
   - Clean obsidian surfaces with subtle 1px borders.
   - Status badges with pill shapes and status dot indicators.

## 5. Responsive Behavior
- **Desktop (>= 1280px):** Full multi-column grid, horizontal navigation bar with all destinations.
- **Tablet (768px - 1279px):** 2-column dashboard layout, compact camera HUD, collapsed secondary sidebars.
- **Mobile (< 768px):** Single-column stacked layout, slide-over drawer navigation, touch-optimized control pads.
