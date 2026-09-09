#!/usr/bin/env bash
# deps.sh — Cross-component dependency graph generator
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

echo '```mermaid'
echo 'graph LR'

for comp_dir in "$PROJECT_ROOT"/apps/*/; do
  name=$(basename "$comp_dir")
  pkg="$comp_dir/package.json"

  if [ -f "$pkg" ]; then
    # Internal cross-component dependencies via workspace references
    python3 -c "
import json
d = json.load(open('$pkg'))
for dep_type in ['dependencies', 'devDependencies']:
    for dep in d.get(dep_type, {}):
        if dep.startswith('@') or dep.startswith('packages/'):
            print(f'  {name} -->|depends| {dep}')
" 2>/dev/null || true
  fi
done

echo '```'
