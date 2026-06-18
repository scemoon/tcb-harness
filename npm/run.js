#!/usr/bin/env node
const { spawn, execSync } = require('child_process');
const path = require('path');

function exec(cmd, opts = {}) {
  try {
    return { ok: true, out: execSync(cmd, { stdio: 'pipe', ...opts }).toString().trim() };
  } catch (e) {
    return { ok: false, out: e.stderr?.toString() || e.message };
  }
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

function run(pythonModule) {
  const PKG_DIR = __dirname;
  const PYTHON_ENV_DIR = path.join(require('os').homedir(), '.onecode', 'python');

  const isPostinstall = process.argv.length <= 2;
  const py = checkPython();

  if (!py.ok) {
    console.error(`cdh: Python ${py.version || 'not found'}, version 3.14+ is required.`);

    if (checkUv()) {
      console.log('cdh: Creating Python environment with uv...');
      exec(`uv venv "${PYTHON_ENV_DIR}"`);
      const venvPython = path.join(PYTHON_ENV_DIR, 'bin', 'python');
      console.log('cdh: Installing cloud-dev-harness...');
      exec(`"${venvPython}" -m pip install -e "${PKG_DIR}"`);
      if (isPostinstall) {
        console.log('cdh: Installed. Add to PATH: export PATH="$HOME/.onecode/python/bin:$PATH"');
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
    console.log('cdh: Installing cloud-dev-harness...');
    exec(`${py.pythonCmd} -m pip install "${PKG_DIR}"`);
  }

  if (isPostinstall) {
    console.log('cdh: Installed. Run "cdh" to start.');
    process.exit(0);
  }

  const args = process.argv.slice(2).filter(a => !a.startsWith('--'));
  const cmd = spawn(py.pythonCmd, ['-m', pythonModule, ...args], {
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
