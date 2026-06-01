# Git Skill

Provides Git version control and GitHub integration capabilities.

## Agent Tools

| Operation | Tool |
|-----------|------|
| Clone repo | `exec_shell("git clone ...")` |
| Commit | `exec_shell("git commit ...")` |
| Push/Pull | `exec_shell("git push/pull")` |
| Branch | `exec_shell("git checkout/branch ...")` |
| GitHub API | via `gh` command |

## Common Commands

### Basic Workflow
```bash
git init                    # Initialize repo
git clone <url>             # Clone repository
git add .                   # Stage all changes
git commit -m "message"     # Commit with message
git push                    # Push to remote
git pull                    # Pull from remote
```

### Branching
```bash
git branch                  # List branches
git branch -b new-branch    # Create and switch
git checkout <branch>       # Switch branch
git merge <branch>          # Merge branch
```

### Inspection
```bash
git status                  # Show working tree status
git log --oneline -10       # Recent commits
git diff                    # Show changes
git diff --staged           # Staged changes
git show <commit>           # Commit details
```

### GitHub CLI (`gh`)
```bash
gh repo clone owner/repo    # Clone via gh
gh pr create                # Create pull request
gh pr list                  # List PRs
gh issue list               # List issues
gh repo view                # View repo info
```

## Agent Integration

When this skill is active, the agent can:
1. Clone repos to local via `git clone`
2. Commit changes with structured messages
3. Create and manage branches
4. Interact with GitHub via `gh` CLI
5. Pull/push code during development

## GitHub Token

Store token at `~/.cloud-harness-tokens.json` or set `GITHUB_TOKEN` env var.