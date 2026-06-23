#!/usr/bin/env bash
#
# Package the SwiftPM executable into a launchable "Agent Hooks.app" bundle.
#
#   ./scripts/build_app.sh             # builds macos/build/Agent Hooks.app
#   ./scripts/build_app.sh --install   # also copies it to ~/Applications (Spotlight-indexed)
#
# A bare `swift build` only emits a Unix executable; Spotlight / Finder / Launchpad only
# launch .app bundles, so this wraps the binary with an Info.plist and an ad-hoc signature.
set -euo pipefail

APP_NAME="Agent Hooks"
BUNDLE_ID="dev.zhu424.agent-hooks.ui"
EXECUTABLE="agent-hooks-ui"
VERSION="0.3.0"
CONFIG="release"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(dirname "$SCRIPT_DIR")"
OUT_DIR="$PKG_DIR/build"
APP="$OUT_DIR/$APP_NAME.app"

echo "==> swift build -c $CONFIG"
swift build --package-path "$PKG_DIR" -c "$CONFIG"
BIN_DIR="$(swift build --package-path "$PKG_DIR" -c "$CONFIG" --show-bin-path)"

echo "==> assembling $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN_DIR/$EXECUTABLE" "$APP/Contents/MacOS/$EXECUTABLE"

echo "==> generating app icon"
ICONSET="$OUT_DIR/AppIcon.iconset"
rm -rf "$ICONSET"
"$BIN_DIR/$EXECUTABLE" --write-iconset "$ICONSET"
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"
rm -rf "$ICONSET"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>
    <string>$APP_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>$BUNDLE_ID</string>
    <key>CFBundleExecutable</key>
    <string>$EXECUTABLE</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleVersion</key>
    <string>$VERSION</string>
    <key>CFBundleShortVersionString</key>
    <string>$VERSION</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST

echo "==> ad-hoc code signing"
codesign --force --sign - "$APP"

echo "built: $APP"

if [[ "${1:-}" == "--install" ]]; then
    DEST="$HOME/Applications"
    mkdir -p "$DEST"
    rm -rf "$DEST/$APP_NAME.app"
    cp -R "$APP" "$DEST/"
    echo "installed: $DEST/$APP_NAME.app"
fi
