#!/bin/bash

BUILD_DIR="$( cd "$(dirname "$0")" || exit ; pwd -P )"
TEMP="${BUILD_DIR}"/temp
ROOT="${BUILD_DIR}"/..
MANIFEST="${ROOT}/io_scene_niftools/blender_manifest.toml"
VERSION=$(python -c "import sys, tomllib; print(tomllib.load(open(sys.argv[1], 'rb'))['version'])" "${MANIFEST}")
NAME="blender_niftools_addon"
HASH=$(git rev-parse --short HEAD)
DATE=$(date +%F)
ZIP_NAME="${NAME}-v${VERSION}-${DATE}-${HASH}.zip"

echo "Blender extensions directory : ${BLENDER_EXTENSIONS_DIR}"
if [[ ! -e "${BLENDER_EXTENSIONS_DIR}" ]]; then
    echo Blender extensions folder not found.
    echo "Set BLENDER_EXTENSIONS_DIR to the user_default repository, such as:"
    echo "  export BLENDER_EXTENSIONS_DIR=~/.config/blender/5.2/extensions/user_default"
    echo Start blender at least once, save user preferences, and try again.
    exit 1
else
    echo "Using ${BLENDER_EXTENSIONS_DIR} as installation directory"
fi

NIFTOOLS_ADDON_DIR="${BLENDER_EXTENSIONS_DIR}"/io_scene_niftools
if [[ -d "${NIFTOOLS_ADDON_DIR}" ]]; then
  echo "Installing to: ${NIFTOOLS_ADDON_DIR}"
  echo "Removing old io_scene_niftools directory ${NIFTOOLS_ADDON_DIR}"
  rm -rf "${NIFTOOLS_ADDON_DIR}"
else
  echo "Niftools addon directory does not exist"
  echo "Directory: ${NIFTOOLS_ADDON_DIR}"
fi

# create zip
echo "Creating addon zip file"
sh "${BUILD_DIR}"/makezip.sh || exit 1

# copy files from repository to blender extensions folder
echo "Unzipping to ${NIFTOOLS_ADDON_DIR}"
mkdir -p "${NIFTOOLS_ADDON_DIR}"
unzip -q "${TEMP}/${ZIP_NAME}" -d "${NIFTOOLS_ADDON_DIR}"
