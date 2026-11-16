#!/usr/bin/env bash
# Wrap the PyInstaller output (dist/avilys) into an AppImage.
# Usage, from the repo root:  packaging/linux/build-appimage.sh VERSION [APPIMAGETOOL]
set -euo pipefail

VERSION="${1:?usage: build-appimage.sh VERSION [path/to/appimagetool]}"
TOOL="${2:-appimagetool}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APPDIR="$ROOT/build/avilys.AppDir"

[ -x "$ROOT/dist/avilys/avilys" ] || { echo "run pyinstaller first (dist/avilys missing)" >&2; exit 1; }
[ -f "$ROOT/packaging/build/avilys.png" ] || { echo "run packaging/make_icons.py first" >&2; exit 1; }

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a "$ROOT/dist/avilys" "$APPDIR/usr/lib/avilys"
cp "$ROOT/packaging/linux/avilys.desktop" "$APPDIR/avilys.desktop"
cp "$ROOT/packaging/linux/avilys.desktop" "$APPDIR/usr/share/applications/avilys.desktop"
cp "$ROOT/packaging/build/avilys.png" "$APPDIR/avilys.png"
cp "$ROOT/packaging/build/avilys.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/avilys.png"
ln -s avilys.png "$APPDIR/.DirIcon"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/avilys/avilys" "$@"
EOF
chmod +x "$APPDIR/AppRun"

OUT="$ROOT/dist/avilys-${VERSION}-x86_64.AppImage"
ARCH=x86_64 "$TOOL" --no-appstream "$APPDIR" "$OUT"
echo "built $OUT"
