#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPDIR="${DIR}/AppDir"

echo "=== Cleaning old AppDir ==="
rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin"
mkdir -p "${APPDIR}/usr/share/applications"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/scalable/apps"

echo "=== Copying application files ==="
cp "${DIR}/app.py" "${APPDIR}/usr/bin/app.py"
cp "${DIR}/scanner.py" "${APPDIR}/usr/bin/scanner.py"
cp "${DIR}/installer.py" "${APPDIR}/usr/bin/installer.py"
chmod +x "${APPDIR}/usr/bin/app.py"

cp "${DIR}/linux-app-manager.desktop" "${APPDIR}/linux-app-manager.desktop"
cp "${DIR}/linux-app-manager.desktop" "${APPDIR}/usr/share/applications/linux-app-manager.desktop"

cp "${DIR}/linux-app-manager.svg" "${APPDIR}/linux-app-manager.svg"
cp "${DIR}/linux-app-manager.svg" "${APPDIR}/usr/share/icons/hicolor/scalable/apps/linux-app-manager.svg"

# Create .DirIcon symlink
ln -sf linux-app-manager.svg "${APPDIR}/.DirIcon"

echo "=== Creating AppRun script ==="
cat << 'EOF' > "${APPDIR}/AppRun"
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="${HERE}/usr/bin:${PATH}"
export XDG_DATA_DIRS="${HERE}/usr/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
export PYTHONPATH="${HERE}/usr/bin:${PYTHONPATH}"

# Ensure working directory is outside the temporary AppImage mount
if [ -n "$OWD" ] && [ -d "$OWD" ]; then
    cd "$OWD"
else
    cd "$HOME"
fi

exec python3 "${HERE}/usr/bin/app.py" "$@"
EOF
chmod +x "${APPDIR}/AppRun"

echo "AppDir successfully prepared at: ${APPDIR}"
