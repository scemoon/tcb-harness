# cloud-harness

CloudBase development pipeline tool for WeChat Mini Programs, Web apps, and hybrid projects.

## Quick Start

```bash
# Create new project
python3 cloud-harness/scripts/init_project.py init \
  --name my-project \
  --platform mp \
  --appid wx1234567890abcdef \
  --envId cloud1-xxxxxxxx

# Switch active project
python3 cloud-harness/scripts/init_project.py switch my-project

# Show project status
python3 cloud-harness/scripts/project_status.py

# Validate spec
python3 cloud-harness/scripts/validate_spec.py specs/my-project/requirements.md
```

## Pipeline

```
Init → Spec → Design → Coding (TDD) → Testing → Deploy
```

- **Init:** Scaffold project with `init_project.py`
- **Spec:** Write EARS-format requirements in `specs/`
- **Design:** Write architecture docs in `design/`
- **Coding:** TDD with RED → GREEN → REFACTOR
- **Testing:** Generate cases, ensure ≥80% coverage
- **Deploy:** Backend first, then frontend

## Platform Types

- `mp` — WeChat Mini Program
- `web` — Browser app (TDesign React)
- `oa` — WeChat Official Account H5
- `hybrid` — Multiple platforms sharing backend

## Commands

| Command | Purpose |
|---------|---------|
| `init_project.py init` | Create new project |
| `init_project.py switch` | Set active project |
| `init_project.py import` | Import from GitHub |
| `validate_spec.py` | Validate EARS spec |
| `project_status.py` | Show project progress |

See `SKILL.md` for full documentation.