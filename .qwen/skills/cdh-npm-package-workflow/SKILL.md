---
name: cdh-npm-package-workflow
description: Build and publish cdh npm package with Python shim
source: auto-skill
extracted_at: '2026-06-01T09:39:01.256Z'
---

# CDH NPM Package Workflow

Builds a standalone npm package (`cdh`) that includes all Python modules and a Node.js shim.

## Package Structure

```
npm/
├── cli.js           # Node.js shim - checks Python, installs package, spawns python -m cdh
├── package.json    # npm config
├── .npmignore      # files to exclude from package
└── build-package.sh  # build script
    └── npm_pkg/    # output directory for built .tgz
```

## Build Script Commands

```bash
cd npm
./build-package.sh build      # Build to npm_pkg/cdh-1.0.0.tgz
./build-package.sh publish    # Build + upload to npm + GitHub
./build-package.sh clean      # Clean npm_pkg/
```

## Key Design Decisions

1. **cli.js as shim**: Runs during `postinstall`, checks Python 3.10+, installs Python package
2. **Version variable**: Single source of truth in `build-package.sh` (`VERSION="1.0.0"`)
3. **Flat package structure**: All modules (cdh/, cdha/, tui/, cloud-spec-skill/) at package root
4. **Graceful postinstall failure**: If Python 3.10+ missing during install, logs warning and exits 0 (package files still extracted, user can upgrade Python later)
5. **Output to npm_pkg/**: Not in gitignore by default

## postinstall Flow (cli.js)

1. Check Python version (3.10+ required)
2. If postinstall mode and Python too old → warn + exit 0 (don't fail npm install)
3. If postinstall mode and Python OK + not installed → install Python package
4. If not postinstall → spawn `python3 -m cdh` with args

## NPM Registry

```bash
# Publish to npm
npm publish npm_pkg/cdh-*.tgz

# Or from GitHub Release
gh release upload v1.0.0 npm_pkg/cdh-*.tgz
```