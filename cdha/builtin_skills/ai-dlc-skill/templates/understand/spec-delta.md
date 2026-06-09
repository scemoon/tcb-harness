# Spec Delta — {{change_id}}

## Change Information

| Field | Value |
|-------|-------|
| Change ID | `{{change_id}}` |
| FR ID | `{{fr_id}}` |
| Type | {{type: NEW | ENHANCEMENT | FIX}} |
| Priority | {{priority: P0 | P1 | P2}} |
| Status | Draft → Review → Approved |

## ADDED Requirements

### FR-{{number}}: {{title}}

**Priority:** {{priority}}

**Description (EARS):**
{{ears_description}}

**Acceptance Criteria:**
- AC1: {{positive_case}}
- AC2: {{negative_case}}
- AC3: {{edge_case}}

**BDD Scenarios:**
- `features/{{domain}}/{{feature}}.feature` — @FR-{{number}} @positive
- `features/{{domain}}/{{feature}}.feature` — @FR-{{number}} @negative
- `features/{{domain}}/{{feature}}.feature` — @FR-{{number}} @edge

## MODIFIED Requirements

_(if applicable)_

### FR-{{number}}: {{previous_title}}

**Change:** {{what_changed}}
**Reason:** {{why}}

## REMOVED Requirements

_(if applicable)_

### FR-{{number}}: {{removed_title}}

**Reason:** {{why_removed}}
