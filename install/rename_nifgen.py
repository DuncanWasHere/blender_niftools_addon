"""Rewrite the generated code's internal package name from `generated` to `nifgen`."""

import pathlib
import re
import sys

OLD = "generated"
NEW = "nifgen"

# `from generated...` / `import generated...` at the start of a statement
FROM_RE = re.compile(rf"^(\s*)from {OLD}(\.|\s)", re.M)
IMPORT_RE = re.compile(rf"^(\s*)import {OLD}(\.|\s|$)", re.M)
# Module paths held as string literals, e.g. the name_type_map in each imports.py:
#     'Byte': 'generated.formats.base.basic',
STRING_PATH_RE = re.compile(rf"""(['"]){OLD}\.(?=[A-Za-z_])""")
LOGGER_RE = re.compile(rf"""(getLogger\(["']){OLD}(["'.])""")


def rewrite(path):
    text = original = path.read_text(encoding="utf-8", errors="surrogateescape")
    text = FROM_RE.sub(rf"\1from {NEW}\2", text)
    text = IMPORT_RE.sub(rf"\1import {NEW}\2", text)
    text = STRING_PATH_RE.sub(rf"\g<1>{NEW}.", text)
    text = LOGGER_RE.sub(rf"\g<1>{NEW}.", text)
    if text != original:
        path.write_text(text, encoding="utf-8", errors="surrogateescape")
        return True
    return False


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: rename_nifgen.py <path to nifgen package>")
    root = pathlib.Path(sys.argv[1])
    if not root.is_dir():
        sys.exit(f"not a directory: {root}")

    changed = sum(rewrite(p) for p in root.rglob("*.py"))
    
    print(f"renamed '{OLD}' -> '{NEW}' in {changed} file(s) under {root}")


if __name__ == "__main__":
    main()
