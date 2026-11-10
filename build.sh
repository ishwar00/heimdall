#!/bin/sh
# Builds ~/Applications/Heimdall.app from app/*.swift (needs only Command Line Tools)
# and links the `heimdall` data script to ~/.local/bin/heimdall, where the app runs it from.
set -e
cd "$(dirname "$0")"
APP="$HOME/Applications/Heimdall.app"
mkdir -p "$APP/Contents/MacOS" "$HOME/.local/bin"
ln -sf "$PWD/bin/heimdall" "$HOME/.local/bin/heimdall"
swiftc -O -swift-version 5 app/*.swift -o "$APP/Contents/MacOS/Heimdall"
cp Info.plist "$APP/Contents/Info.plist"
codesign --force --sign - "$APP"
echo "built $APP"
