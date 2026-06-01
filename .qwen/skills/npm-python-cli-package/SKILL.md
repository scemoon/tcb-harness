---
name: npm-python-cli-package
description: Setup npm package wrapper for Python CLI with postinstall pip
source: auto-skill
extracted_at: '2026-06-01T09:14:27.729Z'
---

# NPM Package Wrapper for Python CLI

This skill documents how to create an npm package that wraps a Python CLI tool, installing the Python package via `postinstall` script.

## Key Files

### npm/package.json

```json
{
  "name": "cdh",
  "version": "1.4.0",
  "bin": {
    "cdh": "cli.js"
  },
  "files": [
    "cli.js",
    "cdh/",
    "cdha/",
    "tui/",
    "cloud-spec-skill/",
    "cloud_dev_harness.egg-info"
  ],
  "scripts": {
    "postinstall": "node cli.js"
  }
}
```

### npm/cli.js

```javascript
const PKG_DIR = __dirname;

function checkPython() {
  // Check Python 3.10+ required
}

function installCdh(python) {
  execSync(`${python} -m pip install -e "${PKG_DIR}"`, { stdio: 'inherit' });
}

const python = checkPython();
if (!checkCdhInstalled(python)) {
  installCdh(python);
}

const cmd = spawn(python, ['-m', 'cdh', ...args], { stdio: 'inherit' });
```

## Key Points

1. **PKG_DIR = __dirname** — Must be `__dirname` (local), not `path.resolve(__dirname, '..')` (parent), because npm extracts package to `node_modules/<pkg>/`

2. **files field** — Must explicitly list all Python package directories to include in npm package

3. **postinstall script** — Runs after npm install, executes Python pip install

4. **Python version check** — cli.js should verify Python 3.10+ before attempting pip install

5. **Build script** — Use a shell script to flatten directory structure for npm pack:
   ```bash
   cd package && npm pack && mv cdh-*.tgz "$REPO_ROOT/"
   ```

## Installation Flow

```bash
npm install -g cdh
# → npm extracts cdh-*.tgz to node_modules/cdh/
# → postinstall runs: node cli.js
# → cli.js checks Python version (3.10+)
# → cli.js runs: pip install -e /path/to/cdh
# → cdh command available globally
```

## GitHub Release

```bash
npm pack  # creates cdh-*.tgz
gh release create v1.4.0 cdh-1.4.0.tgz --title "CDH v1.4.0"
```