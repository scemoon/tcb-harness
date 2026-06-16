#!/usr/bin/env bash
# extract-api.sh — Extract API surface from contracts/ directory
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

echo "# API Surface"
echo ""

if [ ! -d "$PROJECT_ROOT/contracts" ]; then
  echo "(No contracts/ directory found)"
  exit 0
fi

# OpenAPI
for f in "$PROJECT_ROOT"/contracts/api/*.yaml "$PROJECT_ROOT"/contracts/api/*.yml; do
  [ -f "$f" ] || continue
  echo "## File: $(basename "$f")"
  python3 -c "
import yaml, json
d = yaml.safe_load(open('$f'))
if 'paths' in d:
    for path, methods in d['paths'].items():
        for method, spec in methods.items():
            print(f\"  {method.upper()} {path} — {spec.get('summary', '?')}\")
if 'info' in d:
    print(f\"  Title: {d['info'].get('title', '?')}\")
    print(f\"  Version: {d['info'].get('version', '?')}\")
" 2>/dev/null || echo "  (parse error)"
  echo ""
done

# AsyncAPI
for f in "$PROJECT_ROOT"/contracts/events/*.yaml "$PROJECT_ROOT"/contracts/events/*.yml; do
  [ -f "$f" ] || continue
  echo "## File: $(basename "$f")"
  python3 -c "
import yaml
d = yaml.safe_load(open('$f'))
channels = d.get('channels', {})
for name, ch in channels.items():
    print(f\"  Channel: {name}\")
" 2>/dev/null || echo "  (parse error)"
  echo ""
done
