# Task List — {{feature_name}}

## Dependency Graph

```mermaid
graph TD
  {{dag_nodes}}
```

## Units

### Unit 1: {{unit_1_name}}

- **Depends on:** none
- **Scenarios:** {{scenario_tags_1}}
- **Tasks:**
  - [ ] {{task_1}}
  - [ ] {{task_2}}
- **Test plan:**
  - `test_{{case_1}}` → {{expected_1}}
  - `test_{{case_2}}` → {{expected_2}}

### Unit 2: {{unit_2_name}}

- **Depends on:** {{unit_1_name}}
- **Scenarios:** {{scenario_tags_2}}
- **Tasks:**
  - [ ] {{task_1}}
  - [ ] {{task_2}}
- **Test plan:**
  - `test_{{case_1}}` → {{expected_1}}
  - `test_{{case_2}}` → {{expected_2}}
