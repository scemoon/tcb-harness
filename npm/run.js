#!/usr/bin/env node
const { spawn, spawnSync, execSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');
const pkg = require('./package.json');

function exec(cmd, opts = {}) {
  try {
    return { ok: true, out: execSync(cmd, { stdio: 'pipe', ...opts }).toString().trim() };
  } catch (e) {
    return { ok: false, out: e.stderr?.toString() || e.message };
  }
}

function execVerbose(cmd, label) {
  if (label) console.log(`cdh: ${label}`);
  const r = spawnSync(cmd, { shell: true, stdio: 'inherit' });
  return { ok: r.status === 0 };
}

function checkPython() {
  const script = 'import sys; v=sys.version_info; print(f"{v.major}.{v.minor}")';
  const r = exec(`python3 -c "${script}"`);
  if (!r.ok) return { ok: false, version: null, pythonCmd: null };
  const [major, minor] = r.out.split('.').map(Number);
  return {
    ok: major > 3 || (major === 3 && minor >= 14),
    version: `${major}.${minor}`,
    pythonCmd: 'python3'
  };
}

function checkUv() {
  const r = exec('uv --version');
  return r.ok;
}

function checkCdhInstalled(pythonCmd) {
  return exec(`${pythonCmd} -m pip show cloud-dev-harness 2>/dev/null`).ok;
}

function uninstallCmd() {
  const cdhDir = path.join(os.homedir(), '.cdh');
  const pythonDir = path.join(cdhDir, 'python');

  console.log('cdh: Uninstalling Cloud Dev Harness...');
  console.log('');

  if (fs.existsSync(pythonDir)) {
    console.log(`cdh: Removing Python environment at ${pythonDir}...`);
    fs.rmSync(pythonDir, { recursive: true, force: true });
  }

  if (fs.existsSync(cdhDir)) {
    console.log(`cdh: Removing global state at ${cdhDir}...`);
    fs.rmSync(cdhDir, { recursive: true, force: true });
  }

  console.log('');
  console.log('cdh: Cleanup complete. To finish uninstall:');
  console.log('');
  console.log('  1. Remove the npm package:');
  console.log('     pnpm remove -g @scemoon/cdh');
  console.log('     # or: npm uninstall -g @scemoon/cdh');
  console.log('');
  console.log('  2. Check your shell config (~/.zshrc, ~/.bashrc, etc.) for:');
  console.log('     export PATH="$HOME/.cdh/python/bin:$PATH"');
  console.log('     Remove this line if present.');
  console.log('');

  process.exit(0);
}

function run(pythonModule) {
  const PKG_DIR = __dirname;
  const PYTHON_ENV_DIR = path.join(os.homedir(), '.cdh', 'python');

  const args = process.argv.slice(2);

  if (args[0] === 'uninstall') {
    uninstallCmd();
    return;
  }

  if (args.includes('--version') || args.includes('-v')) {
    console.log(pkg.version);
    process.exit(0);
  }

  const isPostinstall = process.env.npm_lifecycle_event === 'postinstall' || process.env.npm_command === 'install';
  const py = checkPython();

  if (!py.ok) {
    console.error(`cdh: Python ${py.version || 'not found'}, version 3.14+ is required.`);

    if (checkUv()) {
      if (fs.existsSync(PYTHON_ENV_DIR)) {
        console.log('cdh: Python environment exists, reusing...');
      } else {
        const rv = execVerbose(`uv venv "${PYTHON_ENV_DIR}"`, 'Creating Python environment with uv...');
        if (!rv.ok) {
          console.error('cdh: Failed to create Python environment.');
          process.exit(1);
        }
      }
      const venvPython = path.join(PYTHON_ENV_DIR, 'bin', 'python');
      const ri = execVerbose(`uv pip install "${PKG_DIR}" --python "${venvPython}"`, 'Installing cloud-dev-harness...');
      if (!ri.ok) {
        console.error('cdh: Install failed.');
        process.exit(1);
      }
      if (isPostinstall) {
        console.log('cdh: Installed. Add to PATH: export PATH="$HOME/.cdh/python/bin:$PATH"');
        process.exit(0);
      }
      spawn(venvPython, ['-m', pythonModule, ...process.argv.slice(2)], { stdio: 'inherit' })
        .on('exit', process.exit);
      return;
    }

    console.error('cdh: Install Python 3.14+ or uv (https://github.com/astral-sh/uv).');
    process.exit(isPostinstall ? 0 : 1);
  }

  if (!checkCdhInstalled(py.pythonCmd)) {
    let ri;
    if (checkUv()) {
      ri = execVerbose(`uv pip install "${PKG_DIR}" --python "${py.pythonCmd}"`, 'Installing cloud-dev-harness...');
    } else {
      ri = execVerbose(`${py.pythonCmd} -m pip install "${PKG_DIR}"`, 'Installing cloud-dev-harness...');
    }
    if (!ri.ok) {
      console.error('cdh: Install failed.');
      process.exit(1);
    }
  }

  if (isPostinstall) {
    console.log('cdh: Installed. Run "cdh" to start.');
    process.exit(0);
  }

  const passthroughArgs = process.argv.slice(2).filter(a => a !== '--version' && a !== '-v');
  const cmd = spawn(py.pythonCmd, ['-m', pythonModule, ...passthroughArgs], {
    stdio: 'inherit',
    cwd: PKG_DIR,
  });

  cmd.on('exit', (code) => process.exit(code));
  cmd.on('error', (err) => {
    console.error('cdh: Failed to start:', err.message);
    process.exit(1);
  });
}

module.exports = { run };
