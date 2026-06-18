#!/bin/bash
set -euo pipefail

# Build npm package - self-contained in npm directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
PKG_DIR="$SCRIPT_DIR/npm_pkg"
PKG_FILE="$PKG_DIR/cdh-*.tgz"
VERSION="$(node -e "console.log(require('$SCRIPT_DIR/package.json').version)")"

usage() {
  echo "Usage: $0 [build|publish|clean]"
  echo "  build   - Build npm package to npm_pkg/"
  echo "  publish - Build, publish to npm and GitHub Release"
  echo "  clean   - Remove built package"
  echo ""
  echo "Examples:"
  echo "  $0 build              # Build package to npm_pkg/"
  echo "  $0 publish            # Build, publish to npm and GitHub"
  echo "  $0 publish --dry-run  # Test publish without uploading"
  echo "  $0 clean              # Remove npm_pkg/"
}

cmd="${1:-build}"
shift || true

case "$cmd" in
  build)
    ;;
  publish|clean)
    ;;
  *)
    usage
    exit 1
    ;;
esac

# Clean
rm -rf "$BUILD_DIR"

if [ "$cmd" = "clean" ]; then
  echo "Cleaned."
  exit 0
fi

# Build
mkdir -p "$BUILD_DIR/package" "$PKG_DIR"
cp "$SCRIPT_DIR/package.json" "$BUILD_DIR/package/"
cp "$SCRIPT_DIR/cli.js" "$BUILD_DIR/package/"
rsync -a --no-implied-dirs "$REPO_ROOT/cdh/" "$BUILD_DIR/package/cdh/"
rsync -a --no-implied-dirs "$REPO_ROOT/onecode/" "$BUILD_DIR/package/onecode/"
rsync -a --no-implied-dirs "$REPO_ROOT/tui/" "$BUILD_DIR/package/tui/"
rsync -a --no-implied-dirs --exclude='.agents' --exclude='.claude' "$REPO_ROOT/ai-dlc-skill/" "$BUILD_DIR/package/ai-dlc-skill/"
cp "$REPO_ROOT/pyproject.toml" "$BUILD_DIR/package/"

cat > "$BUILD_DIR/package/package.json" << EOF
{
  "name": "cdh",
  "version": "${VERSION}",
  "description": "Cloud Dev Harness - cloud-native development Agent framework",
  "keywords": ["ai", "agent", "cloud", "development", "cli", "tui"],
  "license": "MIT",
  "repository": {
    "type": "git",
    "url": "git+https://github.com/scemoon/cloud-dev-harness.git"
  },
  "bin": {
    "cdh": "cli.js",
    "cloud-dev-harness": "cli.js"
  },
  "engines": {
    "node": ">=16.0.0"
  },
  "files": [
    "cli.js",
    "package.json",
    "pyproject.toml",
    "cdh",
    "onecode",
    "tui",
    "ai-dlc-skill"
  ],
  "scripts": {
    "postinstall": "node cli.js"
  }
}
EOF

cd "$BUILD_DIR/package"
npm pack
mv cdh-${VERSION}.tgz "$PKG_DIR/"
cd "$SCRIPT_DIR"
rm -rf "$BUILD_DIR"
echo "Package created: npm_pkg/cdh-${VERSION}.tgz"

if [ "$cmd" = "publish" ]; then
  if [ "$1" = "--dry-run" ]; then
    echo "Dry run - skipping upload"
  else
    echo "Publishing to npm..."
    npm publish "$PKG_DIR/cdh-${VERSION}.tgz"
    echo "Uploading to GitHub Release v${VERSION}..."
    gh release create "v${VERSION}" "$PKG_DIR/cdh-${VERSION}.tgz" \
      --title "CDH v${VERSION}" \
      --notes "npm package: cdh v${VERSION}"
  fi
fi
