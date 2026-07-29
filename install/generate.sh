#!/bin/bash
set -euo pipefail

python3 codegen.py
rm -rf /output/generated
mkdir -p /output/generated/formats
cd /codegen/cobra-tools/generated || exit 1

cp ./__init__.py /output/generated/
for module in array base_enum base_struct base_version bitfield context io; do
  cp "./${module}.py" "/output/generated/"
done

cp ./formats/__init__.py /output/generated/formats/

# Everything is ~4.3MB while just taking the formats we need is just ~2.8MB
mv ./formats/base /output/generated/formats
mv ./formats/dds /output/generated/formats
mv ./formats/nif /output/generated/formats
mv ./spells /output/generated
mv ./utils /output/generated
echo "Done"
