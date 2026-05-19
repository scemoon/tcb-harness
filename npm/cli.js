#!/usr/bin/env node
const { spawn, execSync } = require('child_process');
const path = require('path');

const PKG_DIR = path.resolve(__dirname, '..');

function checkPython() {
  try {
    execSync('python3 --version', { stdio: 'ignore' });
    return 'python3';
  } catch {
    try {
      execSync('python --version', { stdio: 'ignore' });
      return 'python';
    } catch {
      return null;
    }
  }
}

function checkCdhInstalled(python) {
  try {
    execSync(`${python} -c "import cdh"`, { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

function installCdh(python) {
  console.log('Installing Cloud Dev Harness Python package...');
  try {
    execSync(`${python} -m pip install -e "${PKG_DIR}"`, { stdio: 'inherit' });
    return true;
  } catch {
    try {
      execSync(`${python} -m pip install git+https://github.com/scemoon/cloud-dev-harness.git`, { stdio: 'inherit' });
      return true;
    } catch {
      return false;
    }
  }
}

const python = checkPython();
if (!python) {
  console.error('Error: Python 3 is required but not found.');
  console.error('Install Python 3 from https://python.org and try again.');
  process.exit(1);
}

if (!checkCdhInstalled(python)) {
  console.log('Cloud Dev Harness Python package not found.');
  if (!installCdh(python)) {
    console.error('Failed to install Cloud Dev Harness.');
    process.exit(1);
  }
}

const args = process.argv.slice(2);
const cmd = spawn(python, ['-m', 'cdh', ...args], {
  stdio: 'inherit',
  cwd: PKG_DIR,
});

cmd.on('exit', (code) => process.exit(code));
cmd.on('error', (err) => {
  console.error('Failed to start Cloud Dev Harness:', err.message);
  process.exit(1);
});
