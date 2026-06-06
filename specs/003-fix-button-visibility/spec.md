# Feature Specification: Fix Button Text Visibility

**Feature Branch**: `003-fix-button-visibility`

**Created**: 2026-06-06

**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Button labels are readable in all display modes (Priority: P1)

Users of the finance web app interact with buttons to confirm drafts, reject drafts, confirm batches, navigate between views, and submit forms. In dark mode (or when the OS is set to a dark colour scheme), the button text currently appears invisible because the button background is a light colour but no foreground text colour is explicitly set — the browser inherits a light text colour from the dark-mode theme, producing near-white text on a near-white background.

**Why this priority**: This is a blocker for all dark-mode users. Every primary action in the Drafts view (Confirm, Reject, Confirm all in this batch) is inaccessible until this is fixed.

**Independent Test**: Open the app in a browser with the OS colour scheme set to dark. Every button label must be clearly legible. Switching the OS back to light mode must also show legible labels — the fix must not break light mode.

**Acceptance Scenarios**:

1. **Given** the OS/browser is in dark mode, **When** the Drafts view is loaded, **Then** all button labels ("Confirm", "Reject", "Confirm all in this batch") are visibly readable against the button background.
2. **Given** the OS/browser is in light mode, **When** any view containing buttons is loaded, **Then** all button labels remain clearly readable (no regression).
3. **Given** a button is disabled (e.g. a transaction action while another is in progress), **When** the user views it, **Then** the reduced-opacity disabled state is still distinguishable from the enabled state.
4. **Given** the navigation buttons (view tabs) are present, **When** the user views them in dark mode, **Then** their labels are readable including the active-tab highlighted state.

---

### Edge Cases

- Buttons inside forms (e.g. the new-transaction submit button) must also be legible in both modes.
- The logout button and navigation toggle (hamburger) use `background: transparent` — those must not regress.
- The active nav button has a grey background (`#ddd`) — its label must remain readable in both modes.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: All button labels MUST be readable in both light and dark OS colour-scheme modes at normal viewing distance.
- **FR-002**: The fix MUST apply to all buttons site-wide, not selectively to specific views or individual buttons.
- **FR-003**: Buttons styled with `background: transparent` (logout, nav toggle) MUST NOT be adversely affected by the fix.
- **FR-004**: The disabled button appearance MUST still visually distinguish a disabled button from an enabled one after the fix.
- **FR-005**: The active navigation button highlight MUST remain visually distinct in both colour modes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of buttons in all views show legible text in dark mode — verified manually by switching the OS to dark mode and inspecting each view.
- **SC-002**: 100% of buttons in all views show legible text in light mode — no regression from the current light-mode appearance.
- **SC-003**: The fix is a single, targeted change to the shared button style; no per-component workarounds are introduced.

## Assumptions

- The root cause is the absence of an explicit text colour on the base `button` rule in the shared stylesheet, combined with the `color-scheme: light dark` declaration that allows the browser to inherit a light text colour in dark mode.
- The app does not use a theming system or design token layer — a direct fix to the stylesheet is the correct approach.
- No other colour-scheme-specific styles need to change as part of this fix; only the button text colour is affected.
- The fix targets the existing stylesheet; no new CSS files or utility classes are introduced.
