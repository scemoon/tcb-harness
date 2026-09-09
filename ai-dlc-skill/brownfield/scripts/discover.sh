#!/usr/bin/env bash
# discover.sh — Component discovery for brownfield projects
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

echo "{
  \"components\": ["

first=true
for comp_dir in "$PROJECT_ROOT"/apps/*/; do
  name=$(basename "$comp_dir")
  pkg="$comp_dir/package.json"
  $first || echo ","
  first=false

  if [ -f "$pkg" ]; then
    python3 -c "
import json
d=json.load(open('$pkg'))
print(json.dumps({
    'id': '$name',
    'path': '$comp_dir',
    'name': d.get('name', '$name'),
    'framework': d.get('framework', '?'),
    'language': d.get('language', '?'),
}, indent=2))
" 2>/dev/null || echo "{\"id\": \"$name\", \"path\": \"$comp_dir\"}"
  else
    echo "{\"id\": \"$name\", \"path\": \"$comp_dir\", \"warning\": \"no package.json\"}"
  fi
done

echo "]}"
