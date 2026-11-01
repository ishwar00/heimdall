#!/bin/sh
# Builds ~/Applications/ThreadIsland.app from app/*.swift (needs only Command Line Tools)
# and links the `threads` data script to ~/.local/bin/threads, where the app runs it from.
set -e
cd "$(dirname "$0")"
APP="$HOME/Applications/ThreadIsland.app"
mkdir -p "$APP/Contents/MacOS" "$HOME/.local/bin"
ln -sf "$PWD/threads" "$HOME/.local/bin/threads"
swiftc -O -swift-version 5 app/*.swift -o "$APP/Contents/MacOS/ThreadIsland"
cp Info.plist "$APP/Contents/Info.plist"
codesign --force --sign - "$APP"
echo "built $APP"
