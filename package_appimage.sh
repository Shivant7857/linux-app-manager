#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPDIR="${DIR}/AppDir"
OUTPUT="${DIR}/LinuxAppManager-x86_64.AppImage"

echo "=== 1. Building AppDir ==="
"${DIR}/build_appdir.sh"

echo "=== 2. Compiling AppImage runtime ==="
gcc -O2 -Wall "${DIR}/runtime.c" -o "${DIR}/runtime.bin"

echo "=== 3. Padding runtime to 128KB and applying magic bytes ==="
python3 -c "
with open('${DIR}/runtime.bin', 'r+b') as f:
    f.truncate(131072)
    f.seek(8)
    f.write(b'AI\x02')
"

echo "=== 4. Creating SquashFS filesystem ==="
rm -f "${DIR}/payload.squashfs"
mksquashfs "${APPDIR}" "${DIR}/payload.squashfs" -root-owned -noappend -comp xz

echo "=== 5. Assembling final .AppImage ==="
rm -f "${OUTPUT}"
cat "${DIR}/runtime.bin" "${DIR}/payload.squashfs" > "${OUTPUT}"
chmod +x "${OUTPUT}"

rm -f "${DIR}/runtime.bin" "${DIR}/payload.squashfs"

echo "============================================="
echo " AppImage successfully generated!"
echo " Output: ${OUTPUT}"
echo " Size: $(du -h "${OUTPUT}" | cut -f1)"
echo "============================================="
