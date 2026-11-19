"""Build (and optionally install) the Blender Niftools Addon zip.

Generates nifgen wheel from cobra-tools codegen.
Downloads the PyFFI wheel and zips the add-on with blender_manifest.toml at the root.

Requires Python 3.11+, git, and internet access (if source dependencies are not yet cached under install/.cache/).

Usage:
    python install/build.py                    # build install/temp/<name>.zip
    python install/build.py --install          # build, then install into BLENDER_EXTENSIONS_DIR
    python install/build.py --generated-dir D  # skip codegen, use an existing `generated` tree
"""

import argparse
import datetime
import hashlib
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tomllib
import zipfile

if sys.version_info < (3, 11):
    sys.exit("build.py requires Python 3.11 or newer")


PYTHON_VERSION = "3.13" # Current Blender Python version
TARGETS = {
 "manylinux2014_x86_64",
 "manylinux2014_aarch64",
 "win_amd64",
 "win_arm64",
 "macosx_11_0_arm64",
}

# Source Dependencies
COBRA_REPO = "https://github.com/DuncanWasHere/cobra-tools.git"
COBRA_COMMIT = "e966da4f18b999bbf09fd73a3b4af7f112403e8d"
PYFFI_REPO = "https://github.com/DuncanWasHere/new-pyffi.git"
PYFFI_COMMIT = "dda5fc01fb9aa86ac8b793312ea669ec583068cc"
NIFXML_REPO = "https://github.com/Candoran2/nifxml.git"
NIFXML_COMMIT = "9914a2b4984b4909cbc55512fa8162852b211565"

PYFFI_VERSION = "2.2.4.dev3"
# nifgen wheel version: 0.0.0+<new-pyffi commit>.<content hash>, see nifgen_version()
NIFGEN_BASE_VERSION = "0.0.0"

NAME = "blender_niftools_addon"
INSTALL_DIR = pathlib.Path(__file__).resolve().parent
ROOT = INSTALL_DIR.parent
ADDON_IN = ROOT / "io_scene_niftools"
MANIFEST = ADDON_IN / "blender_manifest.toml"
CACHE = INSTALL_DIR / ".cache"
TEMP = INSTALL_DIR / "temp"

# Only the codegen formats we actually use
KEEP_FORMATS = ("base", "dds", "nif")
GENERATED_MODULES = ("array", "base_enum", "base_struct", "base_version", "bitfield", "context", "io")
DOC_FILES = ("AUTHORS.rst", "CHANGELOG.rst", "LICENSE.rst", "README.rst")
ZIP_EXCLUDE_NAMES = {"__pycache__", ".project", "fileformat.dtd"}


def log(msg):
    print(f"[build] {msg}", flush=True)


def run(cmd, cwd=None):
    log("$ " + " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], cwd=cwd, check=True)


def rmtree(path):
    def fix_readonly(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if not path.exists():
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=fix_readonly)
    else:
        shutil.rmtree(path, onerror=fix_readonly)


def fetch(name, repo, commit):
    dest = CACHE / f"{name}-{commit[:12]}"
    marker = dest / ".build-complete"
    if marker.is_file():
        log(f"using cached {name} @ {commit[:12]}")
        return dest
    rmtree(dest)
    dest.mkdir(parents=True)
    log(f"fetching {name} @ {commit[:12]}")
    run(["git", "init", "-q"], cwd=dest)
    run(["git", "fetch", "-q", "--depth", "1", repo, commit], cwd=dest)
    run(["git", "-c", "advice.detachedHead=false", "checkout", "-q", "FETCH_HEAD"], cwd=dest)
    marker.touch()
    return dest


def copy_tree(src, dst):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", "__pycache__"), dirs_exist_ok=True)


def run_codegen(work):
    cobra = fetch("cobra-tools", COBRA_REPO, COBRA_COMMIT)
    pyffi = fetch("new-pyffi", PYFFI_REPO, PYFFI_COMMIT)
    nifxml = fetch("nifxml", NIFXML_REPO, NIFXML_COMMIT)

    log(f"assembling codegen tree in {work}")
    copy_tree(cobra, work)
    (work / ".build-complete").unlink(missing_ok=True)
    source = work / "source"
    copy_tree(pyffi / "formats" / "nif", source / "formats" / "nif")
    copy_tree(pyffi / "spells", source / "spells")
    copy_tree(pyffi / "utils", source / "utils")
    shutil.copy2(nifxml / "nif.xml", source / "formats" / "nif" / "nif.xml")

    for fmt in (source / "formats").iterdir():
        if fmt.is_dir() and fmt.name not in KEEP_FORMATS:
            rmtree(fmt)

    log("running codegen")
    run([sys.executable, "-m", "codegen", "-g", "nifgen"], cwd=work)
    return work / "nifgen"


def nifgen_version(nifgen):
    digest = hashlib.sha256()
    for path in sorted(p for p in nifgen.rglob("*") if p.is_file()):
        rel = path.relative_to(nifgen).as_posix()
        if "__pycache__" in rel.split("/"):
            continue
        digest.update(rel.encode() + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return f"{NIFGEN_BASE_VERSION}+{PYFFI_COMMIT[:7]}.{digest.hexdigest()[:8]}"


def copy_nifgen(generated, nifgen):
    nifgen.mkdir(parents=True)
    shutil.copy2(generated / "__init__.py", nifgen)
    for module in GENERATED_MODULES:
        shutil.copy2(generated / f"{module}.py", nifgen)
    (nifgen / "formats").mkdir()
    shutil.copy2(generated / "formats" / "__init__.py", nifgen / "formats")
    for fmt in KEEP_FORMATS:
        copy_tree(generated / "formats" / fmt, nifgen / "formats" / fmt)
    for pkg in ("spells", "utils"):
        copy_tree(generated / pkg, nifgen / pkg)


WHEELS_RE = re.compile(r"^wheels\s*=\s*\[.*?\]\s*?\n", re.M | re.S)
TABLE_RE = re.compile(r"^\[", re.M)


def write_manifest_wheels(manifest_path, wheels_dir):
    wheels = sorted(f"./wheels/{p.name}" for p in wheels_dir.glob("*.whl"))
    block = "wheels = [\n" + "".join(f'  "{w}",\n' for w in wheels) + "]\n"
    text = manifest_path.read_text(encoding="utf-8")
    if WHEELS_RE.search(text):
        text = WHEELS_RE.sub(lambda _: block, text, count=1)
    else:
        # wheels key has to go before the first [table]
        table = TABLE_RE.search(text)
        pos = table.start() if table else len(text)
        text = text[:pos] + block + "\n" + text[pos:]
    manifest_path.write_text(text, encoding="utf-8")

    with manifest_path.open("rb") as f:
        written = tomllib.load(f).get("wheels")
    if written != wheels:
        sys.exit(f"failed to write wheels to {manifest_path}: got {written}, expected {wheels}")
    log("manifest wheels: " + ", ".join(wheels))


def make_zip(src, zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(src.rglob("*")):
            rel = path.relative_to(src)
            if any(part in ZIP_EXCLUDE_NAMES or part.startswith(".git") for part in rel.parts):
                continue
            if path.is_file():
                zf.write(path, rel.as_posix())


def git_hash():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "nogit"


def build(args):
    with MANIFEST.open("rb") as f:
        manifest = tomllib.load(f)
    version = manifest["version"]
    date = datetime.date.today().isoformat()
    zip_name = f"{NAME}-v{version}-{date}-{git_hash()}.zip"

    addon_out = TEMP / "io_scene_niftools"
    deps_out = TEMP / "nifgen"
    wheels_out = addon_out / "wheels"

    log(f"building {zip_name}")
    rmtree(TEMP)
    TEMP.mkdir()

    copy_tree(ADDON_IN, addon_out)
    wheels_out.mkdir(exist_ok=True)

    log(f"downloading PyFFI {PYFFI_VERSION} wheel")
    run([sys.executable, "-m", "pip", "download", f"PyFFI=={PYFFI_VERSION}", "--no-deps",
         "--only-binary=:all:", "--dest", wheels_out])

    log(f"downloading lz4 wheel")
    for platform in TARGETS:
        run([sys.executable, "-m", "pip", "download", "lz4", "--python-version", PYTHON_VERSION, "--platform", platform, "--no-deps",
             "--only-binary=:all:", "--dest", wheels_out])

    if args.generated_dir:
        generated = pathlib.Path(args.generated_dir).resolve()
        log(f"using pre-generated tree {generated}")
    else:
        generated = run_codegen(TEMP / "codegen")

    copy_nifgen(generated, deps_out)
    # Blender requires nifgen to be packaged as a wheel
    nifgen_ver = nifgen_version(deps_out)
    log(f"nifgen version {nifgen_ver}")
    run([sys.executable, INSTALL_DIR / "build_nifgen_wheel.py", deps_out, nifgen_ver, wheels_out])

    for doc in DOC_FILES:
        shutil.copy2(ROOT / doc, addon_out)

    write_manifest_wheels(addon_out / "blender_manifest.toml", wheels_out)

    zip_path = TEMP / zip_name
    log(f"creating {zip_path}")
    make_zip(addon_out, zip_path)

    if not args.keep_temp:
        rmtree(TEMP / "codegen")
        rmtree(deps_out)
    return zip_path


def install(zip_path, extensions_dir):
    if not extensions_dir:
        sys.exit("Set BLENDER_EXTENSIONS_DIR (or pass --extensions-dir) to Blender's user_default "
                 "extensions repository, for example:\n"
                 r"  Windows: %APPDATA%\Blender Foundation\Blender\5.3\extensions\user_default" "\n"
                 "  Linux:   ~/.config/blender/5.3/extensions/user_default")
    extensions_dir = pathlib.Path(extensions_dir).expanduser()
    if not extensions_dir.is_dir():
        sys.exit(f"Blender extensions folder not found: {extensions_dir}")
    target = extensions_dir / "io_scene_niftools"
    if target.exists():
        log(f"removing old installation {target}")
        rmtree(target)
    log(f"installing to {target}")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--install", action="store_true",
                        help="install add-on into Blender extensions folder after building")
    parser.add_argument("--extensions-dir", default=os.environ.get("BLENDER_EXTENSIONS_DIR"),
                        help="Blender user_default extensions folder (default: $BLENDER_EXTENSIONS_DIR)")
    parser.add_argument("--generated-dir", default=os.environ.get("GENERATED_FOLDER"),
                        help="use an existing cobra-tools `generated` folder")
    parser.add_argument("--keep-temp", action="store_true",
                        help="don't delete install/temp after packaging")
    parser.add_argument("--clean-cache", action="store_true",
                        help="delete install/.cache and redownload pinned dependency sources before building")
    args = parser.parse_args()

    if args.clean_cache:
        rmtree(CACHE)

    try:
        zip_path = build(args)
        if args.install:
            install(zip_path, args.extensions_dir)
    except subprocess.CalledProcessError as e:
        sys.exit(f"command failed with exit code {e.returncode}")
    log("done")


if __name__ == "__main__":
    main()
