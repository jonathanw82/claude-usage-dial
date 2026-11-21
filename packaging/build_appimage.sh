#!/usr/bin/env bash
# Wrap the PyInstaller folder (dist/claude-usage-dial) into a single-file AppImage.
# Run from the repo root after `pyinstaller packaging/claude-usage-dial.spec`.
# Tools are pinned by version and SHA-256. Set TOOLS_DIR to use already-downloaded copies.
set -euo pipefail

VERSION="${VERSION:?set VERSION, e.g. 0.1.0}"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
APPIMAGETOOL_SHA="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
RUNTIME_URL="https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64"
RUNTIME_SHA="2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d"

TOOLS_DIR="${TOOLS_DIR:-build/tools}"
mkdir -p "$TOOLS_DIR"
fetch() {  # url sha file
  if [ ! -f "$3" ]; then curl -fsSL -o "$3" "$1"; fi
  echo "$2  $3" | sha256sum -c --quiet || { echo "Checksum mismatch for $3" >&2; exit 1; }
}
fetch "$APPIMAGETOOL_URL" "$APPIMAGETOOL_SHA" "$TOOLS_DIR/appimagetool-x86_64.AppImage"
fetch "$RUNTIME_URL" "$RUNTIME_SHA" "$TOOLS_DIR/runtime-x86_64"
chmod +x "$TOOLS_DIR/appimagetool-x86_64.AppImage"

APPDIR=build/AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib"
cp -a dist/claude-usage-dial "$APPDIR/usr/lib/claude-usage-dial"
cp packaging/icon.png "$APPDIR/claude-usage-dial.png"
cat > "$APPDIR/claude-usage-dial.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Claude Usage Dial
Comment=Shows your Claude session and weekly usage
Exec=claude-usage-dial
Icon=claude-usage-dial
Categories=Utility;
Terminal=false
EOF
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/claude-usage-dial/claude-usage-dial" "$@"
EOF
chmod +x "$APPDIR/AppRun"

OUT="dist/Claude-Usage-Dial-${VERSION}-x86_64.AppImage"
# Extract-and-run so this also works where FUSE isn't available (CI containers).
APPIMAGE_EXTRACT_AND_RUN=1 ARCH=x86_64 "$TOOLS_DIR/appimagetool-x86_64.AppImage" \
  --runtime-file "$TOOLS_DIR/runtime-x86_64" "$APPDIR" "$OUT"
echo "Built $OUT"
