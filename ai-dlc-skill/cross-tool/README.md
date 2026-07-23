# Cross-Tool Export

Each subdirectory contains a script that exports AI-DLC rules to a specific AI coding tool.

| Tool | Export Script | Output |
|------|---------------|--------|
| OpenCode | `opencode/export.sh` | `.opencode/skills/ai-dlc-skill/` symlink |
| Cursor | `cursor/export.sh` | `.cursor/rules/ai-dlc-core.mdc` |
| Cline | `cline/export.sh` | `.clinerules` |
| Copilot | `copilot/export.sh` | `.github/copilot-instructions.md` |

Usage:

```bash
# Export to all tools
./cross-tool/opencode/export.sh
./cross-tool/cursor/export.sh
./cross-tool/cline/export.sh
./cross-tool/copilot/export.sh
```
