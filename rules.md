# DeepVision Engineering & Design Rules

## 1. Design & Aesthetic Rules
1. **Restrained Enterprise Aesthetic:** Adhere to the Reference 2 security product design language. Use deep charcoal and obsidian dark surfaces (`#080c14`, `#0f172a`) paired with restrained emerald indicators (`#10b981`).
2. **Prohibited Visual Patterns:**
   - No purple gradients or generic AI-themed color schemes.
   - No emoji icons in buttons, headers, or status labels.
   - No em dashes ("—") in website copy. Use standard punctuation, colons, or clean bullet points.
   - No placeholder text ("Lorem ipsum", "Coming soon").
   - No fake statistics, fabricated events, or simulated camera demonstrations.
   - No decorative buttons that pretend to work. Controls must perform genuine actions or be omitted/marked disabled.
3. **Information Hierarchy:**
   - Dashboard is an operational summary, not a giant camera view. Keep live preview compact and secondary.
   - Cameras page is the dedicated surveillance workspace featuring the Reference 1 HUD.
   - Each page must have its own distinct layout, controls, and workflows.

## 2. Coding & Architecture Rules
1. **Frontend Architecture:**
   - React components must be modular and page-specific.
   - Centralize all API requests through `frontend/src/services/api.js`.
   - Use CSS custom properties defined in `globals.css` rather than hardcoded ad-hoc styles.
2. **Backend Integrity:**
   - Preserve all existing Django models, views, and URL patterns.
   - Maintain YOLO11n CPU singleton lifecycle (`MODEL_LOAD_COUNT=1`).
   - Do not perform destructive database migrations or SQLite to MySQL cutovers during UI tasks.
3. **Accessibility & Responsive Standards:**
   - Accessible color contrast for all text (WCAG AA).
   - Descriptive `aria-label` attributes on icon-only buttons.
   - Responsive layouts tested at 1440x900 (Desktop) and 390x844 (Mobile).

## 3. Testing & Verification Rules
1. **Autonomous Repair Loop:**
   - Inspect -> Implement -> Build -> Run -> Browser Verify -> Fix -> Regression Test.
2. **Honest Reporting:**
   - Use PASS, FAIL, WARNING, and BLOCKED honestly based on verified evidence.
   - Never report a redesign as complete without real browser visual verification.
