# Plan Rules (PLN-*)

## PLN-001: Design Documentation
**Severity:** MUST
**Description:** Each feature MUST have a design document covering architecture, data model, API contracts, and state machine. For multi-component features, MUST have per-component sections and an integration section.
**Valid:** `aidlc/openspec/changes/{id}/design.md` with `## Component: backend`, `## Component: web`, `## Integration`.
**Invalid:** A single flat architecture section with no per-component concerns.

## PLN-002: Dependency DAG
**Severity:** MUST
**Description:** Units MUST be decomposed with explicit dependency DAG including cross-component edges. A task producing/consuming a contract MUST depend on the corresponding `INT-FR-*` task.
**Valid:** `depends_on: [int-contract-1, be-unit-1]` for a web task consuming the contract.
**Invalid:** Per-component task lists with no cross-component edges.

## PLN-003: Test Plan Before Implementation
**Severity:** MUST
**Description:** Test plans for each scenario MUST be written before implementation and MUST name the test layer (`unit`, `integration`, `e2e`, `cross-stack`, `contract`).
**Valid:** `BE-FR-001 @positive → layer: integration → test_login_valid_credentials`
**Invalid:** A test plan with no layer designation.

## PLN-004: Contract Plan
**Severity:** MUST
**Description:** For each contract change, the design doc MUST identify version impact (additive vs. breaking), consumers affected, and backward-compat strategy.
**Valid:** `INT-FR-001 change: additive, MINOR bump; no consumer migration needed`
**Invalid:** Contract change with no version impact noted.

## PLN-005: Design Tokens Usage
**Severity:** MUST
**Description:** All UI components MUST use Design Tokens (CSS variables) for colors, spacing, typography, and shadows. Hardcoded values are NOT allowed.
**Valid:** `color: var(--color-primary); padding: var(--space-4);`
**Invalid:** `color: #3B82F6; padding: 16px;`
**Reference:** `phases/plan/design_system/design_tokens.md`

## PLN-006: Design System Compliance
**Severity:** MUST
**Description:** All UI components MUST follow the Design System specification including Atomic Design分层, Component Spec模板, and Platform UI规范.
**Valid:** Components documented per `component_spec.md` template with Props, States, Accessibility
**Invalid:** Component without specification or deviating from atomic design hierarchy
**Reference:** `phases/plan/design_system/atomic_design.md`, `phases/plan/design_system/component_spec.md`

## PLN-007: Accessibility Requirements
**Severity:** MUST
**Description:** All UI components MUST meet WCAG 2.1 AA standards including focus management, ARIA attributes, and color contrast ratios.
**Valid:** Focus ring visible, ARIA labels on icon buttons, contrast ratio ≥ 4.5:1
**Invalid:** Missing focus ring, no ARIA label on icon-only button, contrast ratio < 4.5:1
**Reference:** `phases/plan/design_system/accessibility.md`

## PLN-008: Platform-Specific UI
**Severity:** MUST
**Description:** For each affected platform (web/native/desktop/wxa/mya/tta), the design doc MUST reference the corresponding platform UI spec.
**Valid:** `WEB-FR-001 uses responsive breakpoints per platform_ui/web.md`
**Invalid:** Platform UI designed without referencing platform-specific规范
**Reference:** `phases/plan/design_system/platform_ui/{platform}.md`

## PLN-009: Theme System Support
**Severity:** SHOULD
**Description:** All UI components SHOULD support light/dark theme switching via CSS variables without component code changes.
**Valid:** Components styled with CSS variables, theme切换无闪烁
**Invalid:** Hardcoded colors that don't adapt to theme
**Reference:** `phases/plan/design_system/theme_system.md`
