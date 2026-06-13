#!/usr/bin/env bash
# Fetch the PoC reference designs:
#   PicoRV32 (YosysHQ, ISC)        -> reference/picorv32/
#   AES-128  (secworks, BSD)       -> reference/aes/
#
# Both are gitignored.

set -euo pipefail
cd "$(dirname "$0")/.."

PICORV32_REPO="https://github.com/YosysHQ/picorv32.git"
AES_REPO="https://github.com/secworks/aes.git"

PICORV32_DIR="reference/picorv32"
AES_DIR="reference/aes"

if [ ! -d "${PICORV32_DIR}/.git" ]; then
    echo "==> Shallow-cloning ${PICORV32_REPO}"
    git clone --depth=1 "${PICORV32_REPO}" "${PICORV32_DIR}"
else
    echo "==> ${PICORV32_DIR} already cloned"
fi

if [ ! -d "${AES_DIR}/.git" ]; then
    echo "==> Shallow-cloning ${AES_REPO}"
    git clone --depth=1 "${AES_REPO}" "${AES_DIR}"
else
    echo "==> ${AES_DIR} already cloned"
fi

echo ""
echo "==> Done"
echo "    picorv32: ${PICORV32_DIR}  ($(du -sh "${PICORV32_DIR}" 2>/dev/null | awk '{print $1}'))"
echo "    aes:      ${AES_DIR}       ($(du -sh "${AES_DIR}" 2>/dev/null | awk '{print $1}'))"
