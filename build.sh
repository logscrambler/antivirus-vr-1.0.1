#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DIST="$ROOT/dist"

echo "Cleaning dist..."
rm -rf "$DIST"
mkdir -p "$DIST"

echo "Building Go scanner..."
pushd "$ROOT/src/modules/static_scanner" >/dev/null
# Build c-shared library (Windows will create .dll)
go build -buildmode=c-shared -o "$DIST/manta_scanner.dll" .
if [ -f "$DIST/manta_scanner.dll" ]; then
	echo "Built manta_scanner -> $DIST/manta_scanner.dll"
else
	echo "Warning: manta_scanner build did not produce expected file: $DIST/manta_scanner.dll"
fi
popd >/dev/null

echo "Building Rust monitor..."
pushd "$ROOT/src/modules/dynamic_monitor" >/dev/null
cargo build --release
# copy resulting dynamic lib to dist (filename platform dependent)
shopt -s nullglob || true
for f in target/release/manta_monitor.*; do
	echo "Copying $f to $DIST"
	cp "$f" "$DIST/" || true
done
popd >/dev/null

echo "Installing Python dependencies..."
pip install -r "$ROOT/requirements.txt"

echo "Building launcher (PyInstaller)"
# Ensure ascii.txt is bundled into the onefile exe. Windows --add-data uses semicolon separator.
pyinstaller --onefile --add-data "src/launcher/ascii.txt;." src/launcher/main.py

echo "Collecting launcher output into dist..."
# PyInstaller places exe in dist/, move it to our dist dir if present
if [ -f "dist/main.exe" ]; then
	cp dist/main.exe "$DIST/launcher.exe" || true
fi
if [ -f "dist/main" ]; then
	cp dist/main "$DIST/launcher" || true
fi

echo "Build complete. Output in $DIST"
