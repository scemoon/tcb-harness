#!/usr/bin/env node
const { spawn, execSync } = require('child_process');
const path = require('path');

const PKG_DIR = __dirname;
const CDH_PYTHON_DIR = path.join(require('os').homedir(), '.cdh', 'python');

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
    ok: major > 3 || (major === 3 && minor >= 10),
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

function installWithUv() {
  console.log('cdh: Creating Python environment with uv...');
  exec(`uv venv "${CDH_PYTHON_DIR}"`);
  const venvPython = path.join(CDH_PYTHON_DIR, 'bin', 'python');
  console.log('cdh: Installing cloud-dev-harness...');
  exec(`"${venvPython}" -m pip install -e "${PKG_DIR}"`);
  return venvPython;
}

function installWithSystemPython(pythonCmd) {
  console.log('cdh: Installing cloud-dev-harness...');
  exec(`${pythonCmd} -m pip install "${PKG_DIR}"`);
  return pythonCmd;
}

// Main logic
const isPostinstall = process.argv.length <= 2;
const py = checkPython();

if (!py.ok) {
  console.error(`cdh: Python ${py.version || 'not found'}, version 3.10+ is required.`);

  if (checkUv()) {
    const venvPython = installWithUv();
    if (isPostinstall) {
      console.log('cdh: Installed. Add to PATH: export PATH="$HOME/.cdh/python/bin:$PATH"');
      process.exit(0);
    }
    spawn(venvPython, ['-m', 'cdh', ...process.argv.slice(2)], { stdio: 'inherit' })
      .on('exit', process.exit);
    return;
  }

  console.error('cdh: Install Python 3.10+ or uv (https://github.com/astral-sh/uv).');
  process.exit(isPostinstall ? 0 : 1);
}

// Python OK — install if missing
if (!checkCdhInstalled(py.pythonCmd)) {
  installWithSystemPython(py.pythonCmd);
}

if (isPostinstall) {
  console.log('cdh: Installed. Run "cdh" to start.');
  process.exit(0);
}

const args = process.argv.slice(2).filter(a => !a.startsWith('--'));
const cmd = spawn(py.pythonCmd, ['-m', 'cdh', ...args], {
  stdio: 'inherit',
  cwd: PKG_DIR,
});

cmd.on('exit', (code) => process.exit(code));
cmd.on('error', (err) => {
  console.error('cdh: Failed to start:', err.message);
  process.exit(1);
});
