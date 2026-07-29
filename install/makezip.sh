#!/bin/bash

PYFFI_VERSION="2.2.4.dev3"
NAME="blender_niftools_addon"
CUR_DIR=$(pwd)
BUILD_DIR="$( cd "$(dirname "$0")" || exit ; pwd -P )"
ROOT="${BUILD_DIR}"/..
ADDON_IN="${ROOT}"/io_scene_niftools/
MANIFEST="${ADDON_IN}/blender_manifest.toml"
HASH=$(git rev-parse --short HEAD)
VERSION=$(python -c "import sys, tomllib; print(tomllib.load(open(sys.argv[1], 'rb'))['version'])" "${MANIFEST}")
DATE=$(date +%F)
ZIP_NAME="${NAME}-v${VERSION}-${DATE}-${HASH}.zip"
TEMP="${BUILD_DIR}"/temp
# Extension zip needs blender_manifest.toml in the root
ADDON_OUT="${TEMP}"/io_scene_niftools
DEPS_OUT="${ADDON_OUT}"/dependencies
WHEELS_OUT="${ADDON_OUT}"/wheels

echo "Creating Blender Niftools Addon extension zip"

echo "Checking for temp folder: ${TEMP}"
if [[ -d "${TEMP}" ]]; then
  echo "Removing old temp directory"
  rm -rf "${TEMP}"
else
  echo "No existing temp folder"
fi

mkdir "${TEMP}"

echo "Copying io_scene_niftools directory"
cp -r "${ADDON_IN}" "${ADDON_OUT}"

echo "Downloading PyFFI wheel to ${WHEELS_OUT}"
mkdir -p "${WHEELS_OUT}"
python -m pip download "PyFFI==${PYFFI_VERSION}" --no-deps --only-binary=:all: --dest "${WHEELS_OUT}" || exit 1

echo "Generating nifgen into ${DEPS_OUT}"
mkdir -p "${DEPS_OUT}"
docker compose -f "${BUILD_DIR}/docker-compose.yml" up --build \
  --abort-on-container-exit --exit-code-from codegen || exit 1

echo "Copying loose files"
# Docker-compose mounts ${DEPS_OUT} as /output
cp -r "${GENERATED_FOLDER:-${DEPS_OUT}/generated}" "${DEPS_OUT}/nifgen" || exit 1
# Drop the staging copy so the zip does not carry the tree twice
rm -rf "${DEPS_OUT}/generated"
# Rename folder to nifgen
python "${BUILD_DIR}/rename_nifgen.py" "${DEPS_OUT}/nifgen" || exit 1

# Nifgen ships as a wheel to pass Blender policy check
python "${BUILD_DIR}/build_nifgen_wheel.py" "${DEPS_OUT}/nifgen" "${VERSION}" "${WHEELS_OUT}" || exit 1
rm -rf "${DEPS_OUT}"
cp "${ROOT}"/AUTHORS.rst "${ADDON_OUT}"
cp "${ROOT}"/CHANGELOG.rst "${ADDON_OUT}"
cp "${ROOT}"/LICENSE.rst "${ADDON_OUT}"
cp "${ROOT}"/README.rst "${ADDON_OUT}"

echo "Verifying the wheel named in the manifest is present"
python - "${MANIFEST}" "${ADDON_OUT}" <<'EOF' || exit 1
import os, sys, tomllib
manifest, addon = sys.argv[1], sys.argv[2]
with open(manifest, "rb") as f:
    wheels = tomllib.load(f).get("wheels", [])
missing = [w for w in wheels if not os.path.isfile(os.path.join(addon, w))]
if missing:
    sys.exit(f"manifest lists wheels that were not built: {missing}")
print(f"ok, {len(wheels)} wheel(s) present")
EOF

echo "Creating zip ${ZIP_NAME}"
cd "${ADDON_OUT}" || exit 1
zip -9rq "${TEMP}/${ZIP_NAME}" . -x \*/__pycache__/\* -x \*/.git\* -x \*/.project -x \*/fileformat.dtd
cd "${CUR_DIR}" || exit 1
