# Technical Design — {{feature_name}}

## Overview

{{brief_description}}

## Architecture

```
[Client] → [API Gateway] → [Function] → [Database]
```

## Data Model

```python
@dataclass
class {{model_name}}:
    id: str
    {{field_1}}: {{type_1}}
    {{field_2}}: {{type_2}}
```

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| {{field}} | {{type}} | {{constraints}} | {{description}} |

## API Contract

| Method | Path | Request | Response | Status |
|--------|------|---------|----------|--------|
| {{method}} | {{path}} | {{request}} | {{response}} | {{status_code}} |

## State Machine

```
{{state_a}} → {{state_b}} → {{state_c}}
{{state_b}} → {{error_state}}  (on validation failure)
```

## Dependencies

- {{dependency_1}}
- {{dependency_2}}

## BDD Scenarios

- `features/{{domain}}/{{feature}}.feature` — @FR-{{fr_id}} @positive
- `features/{{domain}}/{{feature}}.feature` — @FR-{{fr_id}} @negative
- `features/{{domain}}/{{feature}}.feature` — @FR-{{fr_id}} @edge
