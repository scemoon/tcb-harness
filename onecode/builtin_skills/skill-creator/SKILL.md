---
name: skill-creator
description: Guide for creating new agent skills with proper conventions
enabled: true
triggers:
  - create skill
  - new skill
  - scaffold skill
  - write skill
  - make a skill
  - build a skill
---

# Skill Creator

## When to Use

When the user asks to create, scaffold, or design a new skill for the agent.

## Skill Structure

A skill consists of two files in a directory under `~/.onecode/skills/<name>/`:

```
skill-name/
├── SKILL.md      # Instructions with YAML frontmatter
└── skill.yaml    # Metadata config
```

## Naming Rules

- Lowercase alphanumeric with single hyphens: `^[a-z0-9]+(-[a-z0-9]+)*$`
- 1-64 characters
- Good: `my-skill`, `code-review`, `deploy-aws`
- Bad: `MySkill`, `my--skill`, `-skill`

## SKILL.md Format

Start with YAML frontmatter (between `---` markers), then markdown body:

```markdown
---
name: my-skill
description: What this skill does
enabled: true
triggers:
  - phrase that triggers
  - another trigger
allowed_tools:
  - Bash
  - Read
phases:
  - plan
  - verify
---

# My Skill

## Instructions
...
```

### Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| name | yes | Skill name (matches dir name) |
| description | yes | 1-1024 chars |
| enabled | no | true/false (default true) |
| triggers | no | Phrases that trigger this skill |
| allowed_tools | no | Restrict which tools available |
| arguments | no | Args accepted from user |
| phases | no | Lifecycle phases this applies to |
| license | no | License identifier |
| compatibility | no | Version/engine compatibility |

## Creating a Skill

### Via CLI

```bash
cdh skill create my-skill --description "Description here"
cdh skill create my-skill -d "Short description"
```

### Via API (Python)

```python
from onecode.skills import create_skill_scaffold
create_skill_scaffold(skills_dir, name="my-skill", description="...")
```

### Manual

1. Create `~/.onecode/skills/<name>/` directory
2. Write `SKILL.md` with frontmatter + instructions
3. Write `skill.yaml` with metadata
4. Run `cdh skill list` to verify it shows up

## Best Practices

- Keep SKILL.md focused and actionable
- Use clear headings and bullet lists
- Include concrete examples and code snippets
- Specify triggers so the agent knows when to activate
- Test with `cdh skill enable/disable` toggle
