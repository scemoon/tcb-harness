#!/usr/bin/env node
const { spawn, execSync } = require('child_process');
const path = require('path');

const PKG_DIR = __dirname;
const IS_GLOBAL = PKG_DIR.includes('node_modules');
const CDH_PYTHON_DIR = path.join(require('os').homedir(), '.cdh', 'python');

function exec(cmd, opts = {}) {
  try {
    return { ok: true, out: execSync(cmd, { stdio: 'pipe', ...opts }).toString().trim() };
  } catch (e) {
    return { ok: false, out: e.stderr?.toString() || e.message };
  }
}

function checkPython() {
  const r = exec('python3 -c "import sys; print(f\\"{sys.version_info.major}.{sys.version_info.minor}\\")"');
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
  return exec(`${pythonCmd} -c "import cdh; import cdha; import tui"`).ok;
}

function setupUvVenv() {
  console.log('cdh: Setting up Python environment with uv...');
  // Create dedicated Python env for cdh
  const venvDir = CDH_PYTHON_DIR;
  exec(`uv venv "${venvDir}" --python 3.12`);
  exec(`"${venvDir}/bin/python" -m pip install pip --upgrade`);
  return `${venvDir}/bin/python`;
}

function installWithUv(pythonCmd) {
  const venvPython = setupUvVenv();
  console.log('cdh: Installing cdh with uv...');
  exec(`"${venvPython}" -m pip install -e "${PKG_DIR}"`);
  return venvPython;
}

function installWithSystemPython(pythonCmd) {
  console.log('cdh: Installing cdh...');
  exec(`${pythonCmd} -m pip install -e "${PKG_DIR}"`);
  return pythonCmd;
}

// Main logic
const isPostinstall = process.argv.length <= 2;
const py = checkPython();

if (!py.ok) {
  console.error(`cdh: Python ${py.version} found, but Python 3.10+ is required.`);
  
  if (checkUv()) {
    console.log('cdh: Using uv to set up Python 3.12 environment...');
    const venvPython = installWithUv();
    if (isPostinstall) {
      console.log('cdh: Installed. Add to PATH: export PATH="$HOME/.cdh/python/bin:$PATH"');
      process.exit(0);
    }
    const args = process.argv.slice(2).filter(a => !a.startsWith('--'));
    spawn(venvPython, ['-m', 'cdh', ...args], { stdio: 'inherit' }).on('exit', process.exit);
    return;
  }
  
  console.error('cdh: Please upgrade Python to 3.10+ or install uv: https://github.com/astral-sh/uv');
  if (isPostinstall) process.exit(0);
  process.exit(1);
}

// Python is OK, check if cdh is installed
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
